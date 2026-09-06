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
from alaya.confirm import ConfirmError, guard

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


# --- Confirmation previews ---

def _wikilink_key_for(src: Path, content: str, backend=None) -> str:
    """The key other notes use to link to this note."""
    if backend:
        return backend.note_link_key(src, content)
    match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
    key = match.group(1).strip() if match else src.stem
    if len(key) >= 2 and key[0] == key[-1] and key[0] in ('"', "'"):
        key = key[1:-1]
    return key


def preview_move(relative_path: str, destination_dir: str, vault: Path) -> str:
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")
    dest = _validate_directory(destination_dir, vault) / src.name
    lines = [f"Move `{relative_path}` -> `{dest.relative_to(vault)}`"]
    if dest.exists():
        lines.append("WARNING: a note already exists at that path; the move will fail.")
    lines.append("Wikilinks are unaffected — only the file location changes.")
    return "\n".join(lines)


def preview_rename(relative_path: str, new_title: str, vault: Path, backend=None) -> str:
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    content = src.read_text()
    old_key = _wikilink_key_for(src, content, backend)
    dest = src.parent / f"{_slugify(new_title)}.md"

    lines = [
        f"Rename `{relative_path}` -> `{dest.relative_to(vault)}`",
        f"Frontmatter title: {old_key!r} -> {new_title!r}",
    ]
    if dest.exists() and dest != src:
        lines.append("WARNING: a note already exists at that path; the rename will fail.")

    # Every note whose wikilinks this rewrites.
    pattern = re.compile(r"\[\[" + re.escape(old_key) + r"\]\]")
    affected = []
    for md_file in _iter_vault_md(vault):
        try:
            hits = len(pattern.findall(md_file.read_text()))
        except OSError as e:
            logger.warning("Skipping %s during rename preview: %s", md_file, e)
            continue
        if hits:
            affected.append((str(md_file.relative_to(vault)), hits))

    if affected:
        total = sum(h for _, h in affected)
        lines.append(f"\nWikilinks rewritten: {total} in {len(affected)} note(s):")
        lines += [f"  - `{path}` ({hits} link{'s' if hits != 1 else ''})" for path, hits in sorted(affected)]
    else:
        lines.append("\nNo other note links to this one; no wikilinks will change.")
    return "\n".join(lines)


def preview_delete(relative_path: str, vault: Path, reason: str | None = None,
                   archives_dir: str = _DEFAULT_ARCHIVES_DIR) -> str:
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    content = src.read_text()
    key = _wikilink_key_for(src, content)
    lines = [
        f"Archive `{relative_path}` -> `{archives_dir}/{src.name}` (soft delete, the file is moved not erased)",
    ]
    if reason:
        lines.append(f"Recorded reason: {reason}")

    refs = [r for r in find_references(key, vault) if r["path"] != relative_path]
    if refs:
        lines.append(f"\n{len(refs)} note(s) link to this one and will be left with broken links:")
        lines += [f"  - `{r['path']}`" for r in refs]
    else:
        lines.append("\nNo other note links to this one.")
    return "\n".join(lines)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path, backend=None) -> None:
    _archives = backend.config.archives_dir if backend else _DEFAULT_ARCHIVES_DIR

    @mcp.tool()
    def move_note_tool(path: str, destination: str, confirm_token: str = "") -> str:
        """Move a note to a different directory. Returns the new path.

        Call without confirm_token to preview the move and receive a token,
        then call again with the token to execute.
        """
        try:
            proposal = guard(
                "move_note_tool", {"path": path, "destination": destination}, confirm_token,
                lambda: preview_move(path, destination, vault),
            )
            if proposal:
                return proposal
            return move_note(path, destination, vault)
        except ConfirmError as e:
            return error(INVALID_ARGUMENT, str(e))
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def rename_note_tool(path: str, new_title: str, confirm_token: str = "") -> str:
        """Rename a note and update all wikilinks referencing it. Returns the new path.

        Call without confirm_token to preview every note whose wikilinks would
        change and receive a token, then call again with the token to execute.
        """
        try:
            proposal = guard(
                "rename_note_tool", {"path": path, "new_title": new_title}, confirm_token,
                lambda: preview_rename(path, new_title, vault, backend=backend),
            )
            if proposal:
                return proposal
            return rename_note(path, new_title, vault, backend=backend)
        except ConfirmError as e:
            return error(INVALID_ARGUMENT, str(e))
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def delete_note_tool(path: str, reason: str = "", confirm_token: str = "") -> str:
        """Soft-delete a note by moving it to archives/.

        Call without confirm_token to preview the archive path and any notes
        left with broken links, then call again with the token to execute.
        """
        try:
            proposal = guard(
                "delete_note_tool", {"path": path, "reason": reason}, confirm_token,
                lambda: preview_delete(path, vault, reason=reason or None, archives_dir=_archives),
            )
            if proposal:
                return proposal
            return delete_note(path, vault, reason=reason or None, archives_dir=_archives)
        except ConfirmError as e:
            return error(INVALID_ARGUMENT, str(e))
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool()
    def find_references_tool(
        title: str, include_text_mentions: bool = False, unbounded: bool = False
    ) -> str:
        """Find all notes that reference the given title as a wikilink or text mention.

        Output is capped; pass unbounded=True to bypass the cap.
        """
        results = find_references(title, vault, include_text_mentions)
        if not results:
            return f"No references to '{title}' found."
        lines = [f"- `{r['path']}` ({r['type']})" for r in results]
        return "\n".join(lines)
