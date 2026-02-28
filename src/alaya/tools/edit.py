"""Edit tools: replace_section, extract_section."""
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT, SECTION_NOT_FOUND, ALREADY_EXISTS
from alaya.vault import resolve_note_path
from alaya.tools.write import create_note


def _parse_sections(content: str) -> list[tuple[str, int, int]]:
    """Return list of (header_text, start_line_idx, end_line_idx) for each ## section.

    end_line_idx is exclusive (points to next header line or EOF).
    """
    lines = content.splitlines()
    sections = []
    for i, line in enumerate(lines):
        if line.startswith("## "):
            header = line[3:].strip()
            sections.append((header, i, None))

    # fill in end indices
    result = []
    for idx, (header, start, _) in enumerate(sections):
        end = sections[idx + 1][1] if idx + 1 < len(sections) else len(lines)
        result.append((header, start, end))

    return result


def replace_section(
    relative_path: str,
    section: str,
    new_content: str,
    vault: Path,
) -> None:
    """Replace the body of a ## section with new_content.

    Raises ValueError with 'SECTION_NOT_FOUND' if the section header doesn't exist.
    """
    path = resolve_note_path(relative_path, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")

    content = path.read_text()
    lines = content.splitlines()
    sections = _parse_sections(content)

    match = next((s for s in sections if s[0].lower() == section.lower()), None)
    if match is None:
        raise ValueError(f"SECTION_NOT_FOUND: '{section}' in {relative_path}")

    header_text, start, end = match

    # rebuild: everything before section body + header + new content + rest
    header_line = lines[start]
    before = lines[:start]
    after = lines[end:]

    new_lines = before + [header_line, new_content] + ([""] if after else []) + after
    path.write_text("\n".join(new_lines) + "\n")


def extract_section(
    source: str,
    section: str,
    new_title: str,
    new_directory: str,
    vault: Path,
) -> str:
    """Extract a ## section into a new note and leave a wikilink in its place.

    Returns the relative path of the new note.
    """
    path = resolve_note_path(source, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {source}")

    content = path.read_text()
    lines = content.splitlines()
    sections = _parse_sections(content)

    match = next((s for s in sections if s[0].lower() == section.lower()), None)
    if match is None:
        raise ValueError(f"SECTION_NOT_FOUND: '{section}' in {source}")

    _, start, end = match
    # body lines are the lines after the header line up to end
    body_lines = lines[start + 1:end]
    body = "\n".join(body_lines).strip()

    # create new note with the extracted content
    from alaya.tools.write import _slugify
    new_path = create_note(
        title=new_title,
        directory=new_directory,
        tags=[],
        body=body,
        vault=vault,
    )

    # replace section body in original with a wikilink
    slug = _slugify(new_title)
    replace_section(source, section, f"[[{slug}]]", vault)

    return new_path


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def replace_section_tool(path: str, section: str, new_content: str) -> str:
        """Replace the content of a named ## section in a note."""
        try:
            replace_section(path, section, new_content, vault)
            return f"Section '{section}' updated in `{path}`."
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            msg = str(e)
            if "SECTION_NOT_FOUND" in msg:
                return error(SECTION_NOT_FOUND, msg)
            return error(OUTSIDE_VAULT, msg)

    @mcp.tool()
    def extract_section_tool(source: str, section: str, new_title: str, new_directory: str) -> str:
        """Extract a ## section into a new note, leaving a wikilink in the original."""
        try:
            new_path = extract_section(source, section, new_title, new_directory, vault)
            return f"Extracted '{section}' from `{source}` → `{new_path}`."
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except FileExistsError as e:
            return error(ALREADY_EXISTS, str(e))
        except ValueError as e:
            msg = str(e)
            if "SECTION_NOT_FOUND" in msg:
                return error(SECTION_NOT_FOUND, msg)
            return error(OUTSIDE_VAULT, msg)

