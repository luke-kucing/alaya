"""Read tools: get_note, list_notes, get_backlinks, get_links, get_tags, reindex_vault."""
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT, INVALID_ARGUMENT
from alaya.vault import resolve_note_path, parse_note
from alaya.zk import run_zk, ZKError, _reject_flag


def _tsv(line: str, count: int) -> tuple[str, ...]:
    """Split a TSV line and return exactly *count* fields, padding with empty strings."""
    parts = line.split("\t")
    return tuple(parts[i] if i < len(parts) else "" for i in range(count))


def _run_reindex(vault: Path):
    from alaya.index.reindex import reindex_all
    return reindex_all(vault)


def reindex_vault(vault: Path, confirm: bool = False) -> str:
    """Rebuild the full LanceDB vector index for the vault.

    Requires confirm=True to prevent accidental triggering.
    """
    if not confirm:
        return "Reindex requires confirm=True. This will rebuild the entire vector index."
    try:
        result = _run_reindex(vault)
        return (
            f"Reindex complete: {result.notes_indexed} notes, "
            f"{result.chunks_created} chunks in {result.duration_seconds}s."
        )
    except Exception as e:
        return f"Reindex failed: {e}"


def _format_note(relative_path: str, content: str) -> str:
    """Format a note with a structured metadata header above the body."""
    note = parse_note(content)
    title = note.title or Path(relative_path).stem
    tags_raw = " ".join(f"#{t}" for t in note.tags)

    lines = [f"**Title:** {title}", f"**Date:** {note.date}"]
    if tags_raw:
        lines.append(f"**Tags:** {tags_raw}")
    lines.append(f"**Path:** {relative_path}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(note.body.strip())
    return "\n".join(lines)


def get_note(relative_path: str, vault: Path) -> str:
    """Return a note's content with a structured metadata header."""
    path = resolve_note_path(relative_path, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")
    return _format_note(relative_path, path.read_text())


def get_note_by_title(title: str, vault: Path) -> str:
    """Find a note by its frontmatter title and return formatted content.

    Raises FileNotFoundError if no match, ValueError if multiple matches.
    """
    from alaya.tools.structure import _iter_vault_md
    title_lower = title.lower()
    matches = []
    for md_file in _iter_vault_md(vault):
        try:
            content = md_file.read_text()
        except OSError:
            continue
        note = parse_note(content)
        note_title = note.title or md_file.stem
        if note_title.lower() == title_lower:
            matches.append((md_file, content))

    if not matches:
        raise FileNotFoundError(f"No note found with title: {title!r}")
    if len(matches) > 1:
        paths = ", ".join(str(f.relative_to(vault)) for f, _ in matches)
        raise ValueError(f"Ambiguous title {title!r} — matches: {paths}")

    md_file, content = matches[0]
    relative_path = str(md_file.relative_to(vault))
    return _format_note(relative_path, content)


def list_notes(
    vault: Path,
    directory: str | None = None,
    tag: str | None = None,
    limit: int = 50,
    since: str | None = None,
    until: str | None = None,
    recent: int | None = None,
    sort: str | None = None,
) -> str:
    """Return a Markdown table of notes, optionally filtered/sorted.

    since/until: ISO date strings for modification date range.
    recent: shorthand for notes modified in the last N days.
    sort: one of 'modified', 'created', 'title'.
    """
    from datetime import date, timedelta

    if since and recent is not None:
        raise ValueError("since and recent are exclusive — use one or the other, not both")

    args = ["list", "--format", "{{path}}\t{{title}}\t{{format-date created '%Y-%m-%d'}}\t{{tags}}", "--limit", str(limit)]

    if tag:
        args += ["--tag", _reject_flag(tag, "tag")]
    if since:
        args += ["--modified-after", _reject_flag(since, "since")]
    if recent is not None:
        cutoff = (date.today() - timedelta(days=recent)).isoformat()
        args += ["--modified-after", cutoff]
    if until:
        args += ["--modified-before", _reject_flag(until, "until")]
    if sort:
        args += ["--sort", _reject_flag(sort, "sort")]
    if directory:
        args += ["--", _reject_flag(directory, "directory")]

    raw = run_zk(args, vault)
    if not raw:
        return "No notes found."

    rows = []
    for line in raw.splitlines():
        path, title, date_str, tags = _tsv(line, 4)
        rows.append(f"| [[{title}]] | `{path}` | {date_str} | {tags} |")

    header = "| Title | Path | Date | Tags |\n|---|---|---|---|"
    return header + "\n" + "\n".join(rows)


def get_backlinks(relative_path: str, vault: Path) -> str:
    """Return a Markdown list of notes that link to the given note."""
    resolve_note_path(relative_path, vault)  # validates path safety
    try:
        raw = run_zk(["list", "--link-to", relative_path, "--format", "{{path}}\t{{title}}"], vault)
    except ZKError:
        return "No backlinks found."

    if not raw:
        return "No backlinks found."

    lines = []
    for line in raw.splitlines():
        path, title = _tsv(line, 2)
        lines.append(f"- [[{title or path}]] (`{path}`)")

    return "\n".join(lines)


def get_links(relative_path: str, vault: Path) -> str:
    """Return a Markdown list of notes that the given note links to."""
    resolve_note_path(relative_path, vault)  # validates path safety
    try:
        raw = run_zk(["list", "--linked-by", relative_path, "--format", "{{path}}\t{{title}}"], vault)
    except ZKError:
        return "No links found."

    if not raw:
        return "No links found."

    lines = []
    for line in raw.splitlines():
        path, title = _tsv(line, 2)
        lines.append(f"- [[{title or path}]] (`{path}`)")

    return "\n".join(lines)


def get_tags(vault: Path) -> str:
    """Return a Markdown table of all tags in the vault with counts."""
    raw = run_zk(["tag", "list", "--format", "{{name}}\t{{note-count}}"], vault)
    if not raw:
        return "No tags found."

    rows = []
    for line in raw.splitlines():
        name, count = _tsv(line, 2)
        rows.append(f"| #{name} | {count or '0'} |")

    header = "| Tag | Notes |\n|---|---|"
    return header + "\n" + "\n".join(rows)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def get_note_tool(path: str = "", title: str = "") -> str:
        """Read a note. Provide exactly one of path (relative path) or title (frontmatter title)."""
        if path and title:
            return error(INVALID_ARGUMENT, "Provide path or title, not both.")
        if not path and not title:
            return error(INVALID_ARGUMENT, "Either path or title is required.")
        try:
            if title:
                return get_note_by_title(title, vault)
            return get_note(path, vault)
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

    @mcp.tool()
    def list_notes_tool(
        directory: str = "",
        tag: str = "",
        limit: int = 50,
        since: str = "",
        until: str = "",
        recent: int = 0,
        sort: str = "",
    ) -> str:
        """List notes. Filter by directory, tag, date range (since/until) or recent N days. Sort by modified/created/title."""
        try:
            return list_notes(
                vault,
                directory=directory or None,
                tag=tag or None,
                limit=limit,
                since=since or None,
                until=until or None,
                recent=recent or None,
                sort=sort or None,
            )
        except ValueError as e:
            return error(INVALID_ARGUMENT, str(e))

    @mcp.tool()
    def get_backlinks_tool(path: str) -> str:
        """Return all notes that link to the given note (backlinks)."""
        return get_backlinks(path, vault)

    @mcp.tool()
    def get_links_tool(path: str) -> str:
        """Return all notes that the given note links to (outgoing links)."""
        return get_links(path, vault)

    @mcp.tool()
    def get_tags_tool() -> str:
        """Return all tags in the vault with note counts."""
        return get_tags(vault)

    @mcp.tool()
    def reindex_vault_tool(confirm: bool = False) -> str:
        """Rebuild the full LanceDB vector index. Requires confirm=True."""
        return reindex_vault(vault, confirm=confirm)

