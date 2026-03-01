"""Structure tools: move_note, rename_note, delete_note, find_references."""
import re
import shutil
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT, INVALID_ARGUMENT
from alaya.events import emit, NoteEvent, EventType
from alaya.vault import resolve_note_path
from alaya.tools.write import _validate_directory, _slugify
from alaya.tools._locks import get_path_lock, atomic_write

_ARCHIVES_DIR = "archives"


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


def find_and_replace_wikilinks(old_title: str, new_title: str, vault: Path) -> list[str]:
    """Replace [[old_title]] with [[new_title]] across all markdown files.

    Returns list of relative paths of files that were updated.
    """
    pattern = re.compile(r"\[\[" + re.escape(old_title) + r"\]\]")
    updated = []
    for md_file in vault.rglob("*.md"):
        content = md_file.read_text()
        new_content, count = pattern.subn(f"[[{new_title}]]", content)
        if count:
            md_file.write_text(new_content)
            updated.append(str(md_file.relative_to(vault)))
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
    for md_file in vault.rglob("*.md"):
        content = md_file.read_text()
        rel = str(md_file.relative_to(vault))

        if wikilink_pattern.search(content):
            results.append({"path": rel, "type": "wikilink"})
        elif text_pattern and text_pattern.search(content):
            results.append({"path": rel, "type": "text"})

    return results


def move_note(relative_path: str, destination_dir: str, vault: Path) -> str:
    """Move a note to destination_dir. Returns the new relative path.

    zk uses title-based wikilinks ([[title]]). A directory move changes the
    file path but not the title, so all existing wikilinks remain valid and
    no vault-wide replacement is needed. Use rename_note when you need to
    update wikilinks.
    """
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    dest_dir = _validate_directory(destination_dir, vault)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.move(str(src), str(dest))
    new_relative = str(dest.relative_to(vault))
    emit(NoteEvent(EventType.MOVED, new_relative, old_path=relative_path))
    return new_relative


def rename_note(relative_path: str, new_title: str, vault: Path) -> str:
    """Rename a note: update title in frontmatter, rename file, update wikilinks vault-wide.

    Returns the new relative path.
    """
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    # Use frontmatter title as the wikilink key; fall back to stem when absent.
    # zk wikilinks reference the note title, not the filename.
    with get_path_lock(src):
        content = src.read_text()
        fm_title_match = re.search(r"^title:\s*(.+)$", content, re.MULTILINE)
        old_title = fm_title_match.group(1).strip() if fm_title_match else src.stem
        new_slug = _slugify(new_title)
        dest = src.parent / f"{new_slug}.md"

        # update frontmatter title then rename atomically
        content = re.sub(r"^title:.*$", f"title: {new_title}", content, count=1, flags=re.MULTILINE)
        atomic_write(src, content)
        src.rename(dest)

    # update all [[old_title]] → [[new_slug]] across vault
    find_and_replace_wikilinks(old_title, new_slug, vault)

    new_relative = str(dest.relative_to(vault))
    emit(NoteEvent(EventType.MOVED, new_relative, old_path=relative_path))
    return new_relative


def delete_note(relative_path: str, vault: Path, reason: str | None = None) -> str:
    """Soft-delete: move note to archives/. Returns the archive path.

    Raises ValueError if the note is already in archives/.
    """
    src = resolve_note_path(relative_path, vault)
    if not src.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    if src.resolve().is_relative_to((vault / _ARCHIVES_DIR).resolve()):
        raise ValueError(f"Note is already archived: {relative_path}")

    if reason:
        with get_path_lock(src):
            existing = src.read_text()
            atomic_write(src, _insert_frontmatter_field(existing, "archived_reason", reason))

    archives_dir = vault / _ARCHIVES_DIR
    archives_dir.mkdir(exist_ok=True)
    dest = archives_dir / src.name

    shutil.move(str(src), str(dest))
    archive_relative = str(dest.relative_to(vault))
    emit(NoteEvent(EventType.DELETED, relative_path))
    return archive_relative


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def move_note_tool(path: str, destination: str) -> str:
        """Move a note to a different directory. Returns the new path."""
        try:
            return move_note(path, destination, vault)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def rename_note_tool(path: str, new_title: str) -> str:
        """Rename a note and update all wikilinks referencing it. Returns the new path."""
        try:
            return rename_note(path, new_title, vault)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def delete_note_tool(path: str, reason: str = "") -> str:
        """Soft-delete a note by moving it to archives/."""
        try:
            return delete_note(path, vault, reason=reason or None)
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

