"""Structure tools: move_note, rename_note, delete_note, find_references."""
import logging
import re
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT, INVALID_ARGUMENT, ALREADY_EXISTS
from alaya.events import emit, NoteEvent, EventType
from alaya.vault import resolve_note_path, iter_vault_md as _iter_vault_md, parse_note
from alaya.tools.write import _validate_directory, _slugify
from alaya.tools._locks import get_path_lock, atomic_write

_DEFAULT_ARCHIVES_DIR = "archives"


def _insert_frontmatter_field(content: str, key: str, value: str) -> str:
    """Insert a key: value field before the closing --- of the frontmatter block.

    If no frontmatter block exists, the content is returned unchanged.
    """
    lines = content.splitlines(keepends=True)
    # find the closing ---
    in_fm = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            if not in_fm:
                in_fm = True
            else:
                # insert just before the closing ---
                lines.insert(i, f"{key}: {value}\n")
                return "".join(lines)
    return content  # no frontmatter found


def find_and_replace_wikilinks(old_key: str, new_key: str, vault: Path) -> list[str]:
    """Replace [[old_key]] with [[new_key]] across all markdown files.

    Returns list of relative paths of files that were updated.
    Skips unreadable files with a warning rather than aborting.
    """
    pattern = re.compile(r"\[\[" + re.escape(old_key) + r"\]\]")
    updated = []
    for md_file in _iter_vault_md(vault):
        try:
            with get_path_lock(md_file):
                content = md_file.read_text()
                replacement = f"[[{new_key}]]"
                new_content, count = pattern.subn(lambda m: replacement, content)
                if count:
                    atomic_write(md_file, new_content)
                    updated.append(str(md_file.relative_to(vault)))
        except OSError as e:
            logger.warning("Skipping %s during wikilink update: %s", md_file, e)
    return updated


def find_references(
    title: str,
    vault: Path,
    include_text_mentions: bool = False,
) -> list[dict]:
    """Return all notes that reference `title` as a wikilink or text mention."""
    wikilink_pattern = re.compile(r"\[\[" + re.escape(title) + r"\]\]")
    text_pattern = re.compile(re.escape(title)) if include_text_mentions else None

    results = []
    for md_file in _iter_vault_md(vault):
        try:
            content = md_file.read_text()
        except OSError as e:
            logger.warning("Skipping %s during reference scan: %s", md_file, e)
            continue
        rel = str(md_file.relative_to(vault))

        if wikilink_pattern.search(content):
            results.append({"path": rel, "type": "wikilink"})
        elif text_pattern and text_pattern.search(content):
            results.append({"path": rel, "type": "text"})

    return results


def move_note(relative_path: str, destination_dir: str, vault: Path) -> str:
    """Move a note to destination_dir. Returns the new relative path."""
    src = resolve_note_path(relative_path, vault)
    dest_dir = _validate_directory(destination_dir, vault)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    with get_path_lock(src):
        if not src.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        if dest.exists():
            raise FileExistsError(f"A note already exists at {dest.relative_to(vault)}")
        shutil.move(str(src), str(dest))
    new_relative = str(dest.relative_to(vault))
    emit(NoteEvent(EventType.MOVED, new_relative, old_path=relative_path))
    return new_relative


def rename_note(relative_path: str, new_title: str, vault: Path, backend=None) -> str:
    """Rename a note: update title in frontmatter, rename file, update wikilinks vault-wide.

    When backend is provided, uses its link resolution strategy to determine
    the wikilink key. Otherwise defaults to frontmatter title (zk behavior).
    """
    src = resolve_note_path(relative_path, vault)

    with get_path_lock(src):
        if not src.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        content = src.read_text()

        if backend:
            old_key = backend.note_link_key(src, content)
        else:
            # Legacy zk behavior: wikilink key is the frontmatter title
            fm_title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
            old_key = fm_title_match.group(1).strip() if fm_title_match else src.stem
            # Strip YAML quoting
            if len(old_key) >= 2 and old_key[0] == old_key[-1] and old_key[0] in ('"', "'"):
                old_key = old_key[1:-1]

        new_slug = _slugify(new_title)
        # nosemgrep: semgrep.alaya-path-traversal -- src from resolve_note_path(), slug from _slugify()
        dest = src.parent / f"{new_slug}.md"
        if dest.exists() and dest != src:
            raise FileExistsError(f"A note already exists at {dest.relative_to(vault)}")

        # update frontmatter title then rename atomically
        content = re.sub(r"^title:.*$", lambda m: f"title: {new_title}", content, count=1, flags=re.MULTILINE)
        atomic_write(src, content)
        src.rename(dest)

    # Determine new wikilink key based on backend strategy
    if backend:
        new_content = dest.read_text()
        new_key = backend.note_link_key(dest, new_content)
    else:
        new_key = new_title

    # update all [[old_key]] -> [[new_key]] across vault
    find_and_replace_wikilinks(old_key, new_key, vault)

    new_relative = str(dest.relative_to(vault))
    emit(NoteEvent(EventType.MOVED, new_relative, old_path=relative_path))
    return new_relative


def delete_note(relative_path: str, vault: Path, reason: str | None = None, archives_dir: str = _DEFAULT_ARCHIVES_DIR) -> str:
    """Soft-delete: move note to archives/. Returns the archive path.

    Raises ValueError if the note is already in archives/.
    """
    src = resolve_note_path(relative_path, vault)
    # nosemgrep: semgrep.alaya-path-traversal -- archives_dir from backend config, validated below
    archive_path = (vault / archives_dir).resolve()
    if not archive_path.is_relative_to(vault.resolve()):
        raise ValueError(f"Archives directory '{archives_dir}' escapes vault root")
    archive_path.mkdir(exist_ok=True)

    with get_path_lock(src):
        if not src.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")

        if src.resolve().is_relative_to(archive_path):
            raise ValueError(f"Note is already archived: {relative_path}")

        if reason:
            existing = src.read_text()
            atomic_write(src, _insert_frontmatter_field(existing, "archived_reason", reason))

        dest = archive_path / src.name
        if dest.exists():
            stem, suffix = src.stem, src.suffix
            counter = 1
            while dest.exists():
                dest = archive_path / f"{stem}-{counter}{suffix}"  # nosemgrep: semgrep.alaya-path-traversal -- archive_path validated on line 161
                counter += 1
        shutil.move(str(src), str(dest))

    archive_relative = str(dest.relative_to(vault.resolve()))
    emit(NoteEvent(EventType.DELETED, relative_path))
    return archive_relative


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path, backend=None) -> None:
    _archives = backend.config.archives_dir if backend else _DEFAULT_ARCHIVES_DIR

    @mcp.tool()
    def move_note_tool(path: str, destination: str) -> str:
        """Move a note to a different directory. Returns the new path."""
        try:
            return move_note(path, destination, vault)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def rename_note_tool(path: str, new_title: str) -> str:
        """Rename a note and update all wikilinks referencing it. Returns the new path."""
        try:
            return rename_note(path, new_title, vault, backend=backend)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def delete_note_tool(path: str, reason: str = "") -> str:
        """Soft-delete a note by moving it to archives/."""
        try:
            return delete_note(path, vault, reason=reason or None, archives_dir=_archives)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool()
    def find_references_tool(title: str, include_text_mentions: bool = False) -> str:
        """Find all notes that reference the given title as a wikilink or text mention."""
        results = find_references(title, vault, include_text_mentions)
        if not results:
            return f"No references to '{title}' found."
        lines = [f"- `{r['path']}` ({r['type']})" for r in results]
        return "\n".join(lines)
