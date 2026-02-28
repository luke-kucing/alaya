"""Write tools: create_note, append_to_note, update_tags."""
import re
from datetime import date
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root
from alaya.vault import resolve_note_path

# Directories considered valid targets for note creation
_VALID_DIRS = {
    "daily", "inbox", "projects", "areas", "people",
    "ideas", "learning", "resources", "raw", "archives",
}


def _validate_directory(directory: str, vault: Path) -> Path:
    """Resolve directory inside vault and reject traversal or unknown dirs."""
    target = (vault / directory).resolve()
    try:
        target.relative_to(vault.resolve())
    except ValueError:
        raise ValueError(f"Directory '{directory}' escapes vault root")
    # allow any subpath under a known top-level dir
    top = target.relative_to(vault.resolve()).parts[0] if target != vault.resolve() else ""
    if top not in _VALID_DIRS:
        raise ValueError(f"Unknown vault directory '{top}'. Expected one of: {sorted(_VALID_DIRS)}")
    return target


def _slugify(title: str) -> str:
    """Convert title to a filename-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug


def create_note(
    title: str,
    directory: str,
    tags: list[str],
    body: str,
    vault: Path,
) -> str:
    """Create a new note and return its relative path."""
    target_dir = _validate_directory(directory, vault)
    target_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(title)
    file_path = target_dir / f"{slug}.md"

    tag_line = " ".join(f"#{t}" for t in tags) if tags else ""

    content_parts = [
        "---",
        f"title: {title}",
        f"date: {date.today().isoformat()}",
        "---",
    ]
    if tag_line:
        content_parts.append(tag_line)
        content_parts.append("")
    if body:
        content_parts.append(body)

    if file_path.exists():
        raise FileExistsError(f"Note already exists: {file_path.relative_to(vault)}")

    file_path.write_text("\n".join(content_parts) + "\n")

    return str(file_path.relative_to(vault))


def append_to_note(relative_path: str, text: str, vault: Path) -> None:
    """Append text to an existing note."""
    path = resolve_note_path(relative_path, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    existing = path.read_text()
    separator = "\n" if existing.endswith("\n") else "\n\n"
    path.write_text(existing + separator + text + "\n")


def update_tags(relative_path: str, add: list[str], remove: list[str], vault: Path) -> None:
    """Add or remove inline #tags from a note.

    Tags are expected on a single line after the frontmatter block.
    If the tag line doesn't exist, a new one is created after the closing ---.
    """
    path = resolve_note_path(relative_path, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    content = path.read_text()

    # find existing inline tag line (first non-empty line after closing ---)
    lines = content.splitlines()
    fm_end = -1
    in_fm = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
            else:
                fm_end = i
                break

    if fm_end == -1:
        # no frontmatter, treat the whole file
        fm_end = -1

    # find the tag line: first line after frontmatter that contains only #words
    tag_line_idx = None
    for i in range(fm_end + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if re.match(r"^(#\w[\w-]* ?)+$", line):
            tag_line_idx = i
        break

    if tag_line_idx is not None:
        existing_tags = set(re.findall(r"#([\w-]+)", lines[tag_line_idx]))
    else:
        existing_tags = set()

    updated_tags = (existing_tags | set(add)) - set(remove)

    # nothing changed — skip the write to avoid reordering tags
    if updated_tags == existing_tags and not add:
        return

    new_tag_line = " ".join(f"#{t}" for t in sorted(updated_tags))

    if tag_line_idx is not None:
        lines[tag_line_idx] = new_tag_line
    else:
        # insert after frontmatter closing ---
        insert_at = fm_end + 1 if fm_end >= 0 else 0
        lines.insert(insert_at, new_tag_line)

    path.write_text("\n".join(lines) + "\n")


# --- FastMCP tool registration ---

def _register(mcp: FastMCP) -> None:
    vault_root = get_vault_root

    @mcp.tool()
    def create_note_tool(title: str, directory: str, tags: list[str], body: str = "") -> str:
        """Create a new note. Returns the relative path of the created file."""
        return create_note(title, directory, tags, body, vault_root())

    @mcp.tool()
    def append_to_note_tool(path: str, text: str) -> str:
        """Append text to an existing note."""
        append_to_note(path, text, vault_root())
        return f"Appended to `{path}`."

    @mcp.tool()
    def update_tags_tool(path: str, add: list[str], remove: list[str]) -> str:
        """Add or remove tags on an existing note."""
        update_tags(path, add, remove, vault_root())
        return f"Tags updated on `{path}`."


try:
    from alaya.server import mcp as _mcp
    _register(_mcp)
except ImportError:
    pass
