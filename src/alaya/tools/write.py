"""Write tools: create_note, append_to_note, update_tags."""
import re
from datetime import date
from pathlib import Path
from alaya.errors import SECTION_NOT_FOUND

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, ALREADY_EXISTS, OUTSIDE_VAULT, INVALID_ARGUMENT
from alaya.events import emit, NoteEvent, EventType
from alaya.vault import resolve_note_path
from alaya.tools._locks import get_path_lock, atomic_write

_DEDUP_THRESHOLD = 0.85


def _check_duplicates(title: str, body: str, vault: Path, threshold: float = _DEDUP_THRESHOLD) -> list[dict]:
    """Return notes with semantic similarity above threshold.

    Uses the same vector search as suggested-links. Returns [] if the index
    is empty or unavailable (never blocks note creation on search failure).
    """
    try:
        from alaya.index.embedder import embed_query
        from alaya.index.store import get_store, hybrid_search

        text = f"{title}. {body[:200]}"
        embedding = embed_query(text)
        store = get_store(vault)
        results = hybrid_search(text, embedding, store, limit=5)
        return [r for r in results if r["score"] >= threshold]
    except Exception:
        return []


def _validate_directory(directory: str, vault: Path) -> Path:
    """Resolve directory inside vault and reject path traversal."""
    # nosemgrep: semgrep.alaya-path-traversal — this function IS the traversal validator
    target = (vault / directory).resolve()
    try:
        target.relative_to(vault.resolve())
    except ValueError:
        raise ValueError(f"Directory '{directory}' escapes vault root")
    return target


def _slugify(title: str) -> str:
    """Convert title to a filename-safe slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug


_VALID_TAG_RE = re.compile(r"^[\w-]+$")


def _load_template(vault: Path, name: str) -> str | None:
    """Load a template file from vault/templates/{name}.md, or None if not found."""
    templates_dir = (vault / "templates").resolve()
    # nosemgrep: semgrep.alaya-path-traversal — validated by is_relative_to() on next line
    path = (templates_dir / f"{name}.md").resolve()
    if not path.is_relative_to(templates_dir):
        raise ValueError(f"Template name {name!r} escapes templates directory")
    try:
        return path.read_text() if path.exists() else None
    except OSError:
        return None


def _render_template(template: str, **variables: str) -> str:
    """Replace {key} placeholders in template with values.

    Uses a single-pass regex to avoid double-substitution (e.g. body
    containing '{title}' being re-expanded).
    """
    known_keys = set(variables.keys())

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in known_keys:
            return variables[key]
        return match.group(0)  # leave unknown placeholders as-is

    return re.sub(r"\{(\w+)\}", _replace, template)


def _build_note_content(
    title: str,
    tags: list[str],
    body: str,
    vault: Path,
    directory: str,
    template: str | None,
) -> str:
    """Build note content from a template or the default inline format."""
    tag_line = " ".join(f"#{t}" for t in tags) if tags else ""
    today = date.today().isoformat()

    # Template lookup: explicit name -> directory name -> default -> inline
    tmpl = (
        (_load_template(vault, template) if template else None)
        or _load_template(vault, directory)
        or _load_template(vault, "default")
    )

    if tmpl:
        return _render_template(
            tmpl,
            title=title,
            date=today,
            tags=tag_line,
            body=body,
            directory=directory,
        )

    # Default inline format (unchanged behaviour when no templates exist)
    parts = ["---", f"title: {title}", f"date: {today}", "---"]
    if tag_line:
        parts.append(tag_line)
        parts.append("")
    if body:
        parts.append(body)
    return "\n".join(parts) + "\n"


def create_note(
    title: str,
    directory: str,
    tags: list[str],
    body: str,
    vault: Path,
    template: str | None = None,
) -> str:
    """Create a new note and return its relative path."""
    slug = _slugify(title)
    if not slug.strip("-"):
        raise ValueError("Title must contain at least one alphanumeric character")

    for tag in tags:
        if not _VALID_TAG_RE.match(tag):
            raise ValueError(f"Invalid tag {tag!r}: tags may only contain letters, digits, underscores, and hyphens")

    target_dir = _validate_directory(directory, vault)
    target_dir.mkdir(parents=True, exist_ok=True)

    # nosemgrep: semgrep.alaya-path-traversal — target_dir from _validate_directory(), slug from _slugify()
    file_path = target_dir / f"{slug}.md"
    content = _build_note_content(title, tags, body, vault, directory, template)

    with get_path_lock(file_path):
        if file_path.exists():
            raise FileExistsError(f"Note already exists: {file_path.relative_to(vault)}")
        atomic_write(file_path, content)

    relative = str(file_path.relative_to(vault))
    emit(NoteEvent(EventType.CREATED, relative))
    return relative


def append_to_note(
    relative_path: str,
    text: str,
    vault: Path,
    section_header: str | None = None,
    dated: bool = False,
) -> None:
    """Append text to an existing note.

    section_header: append under the named '## Header' section instead of EOF.
    dated: prepend a '### YYYY-MM-DD' heading to the appended text.
    """
    path = resolve_note_path(relative_path, vault)

    if dated:
        text = f"### {date.today().isoformat()}\n{text}"

    with get_path_lock(path):
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {relative_path}")

        existing = path.read_text()

        if section_header is None:
            separator = "\n" if existing.endswith("\n") else "\n\n"
            atomic_write(path, existing + separator + text + "\n")
            emit(NoteEvent(EventType.MODIFIED, relative_path))
            return

        # Insert under the named section, before the next ## heading or EOF
        lines = existing.splitlines(keepends=True)
        target = f"## {section_header}"
        section_idx = next(
            (i for i, l in enumerate(lines) if l.rstrip() == target),
            None,
        )
        if section_idx is None:
            raise ValueError(f"Section not found: '{section_header}'")

        # find insertion point: end of this section (before the next ## or EOF)
        insert_at = len(lines)
        for i in range(section_idx + 1, len(lines)):
            if lines[i].startswith("## "):
                insert_at = i
                break

        # inject a blank line + text before the insertion point
        new_lines = lines[:insert_at] + ["\n", text + "\n"] + lines[insert_at:]
        atomic_write(path, "".join(new_lines))

    emit(NoteEvent(EventType.MODIFIED, relative_path))


def update_tags(relative_path: str, add: list[str], remove: list[str], vault: Path) -> None:
    """Add or remove inline #tags from a note.

    Tags are expected on a single line after the frontmatter block.
    If the tag line doesn't exist, a new one is created after the closing ---.
    """
    path = resolve_note_path(relative_path, vault)

    with get_path_lock(path):
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
        if updated_tags == existing_tags:
            return

        new_tag_line = " ".join(f"#{t}" for t in sorted(updated_tags))

        if tag_line_idx is not None:
            lines[tag_line_idx] = new_tag_line
        else:
            # insert after frontmatter closing ---
            insert_at = fm_end + 1 if fm_end >= 0 else 0
            lines.insert(insert_at, new_tag_line)

        atomic_write(path, "\n".join(lines) + "\n")

    emit(NoteEvent(EventType.MODIFIED, relative_path))


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def create_note_tool(
        title: str,
        directory: str,
        tags: list[str],
        body: str = "",
        template: str = "",
        confirm: bool = False,
    ) -> str:
        """Create a new note. Returns the relative path of the created file.

        template: name of a template in vault/templates/ (without .md). Falls back to
        directory name, then 'default', then the built-in inline format.
        confirm: set True to create even when semantically similar notes exist.
        """
        if not confirm:
            dupes = _check_duplicates(title, body, vault)
            if dupes:
                dupe_list = ", ".join(
                    f"[[{d['title']}]] ({d['score']:.0%})" for d in dupes
                )
                return (
                    f"WARNING: Similar notes already exist: {dupe_list}. "
                    "Create anyway with confirm=True."
                )
        try:
            return create_note(title, directory, tags, body, vault, template=template or None)
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool()
    def append_to_note_tool(
        path: str,
        text: str,
        section_header: str = "",
        dated: bool = False,
    ) -> str:
        """Append text to an existing note. Optionally target a section and/or prepend a date heading."""
        try:
            append_to_note(
                path, text, vault,
                section_header=section_header or None,
                dated=dated,
            )
            return f"Appended to `{path}`."
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            # section not found vs path traversal — both map to appropriate error codes
            msg = str(e)
            if "Section" in msg or "section" in msg:
                from alaya.errors import error as _err
                return _err(SECTION_NOT_FOUND, msg)
            return error(OUTSIDE_VAULT, msg)

    @mcp.tool()
    def update_tags_tool(path: str, add: list[str], remove: list[str]) -> str:
        """Add or remove tags on an existing note."""
        try:
            update_tags(path, add, remove, vault)
            return f"Tags updated on `{path}`."
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

