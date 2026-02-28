"""Read tools: get_note, list_notes, get_backlinks, get_links, get_tags, reindex_vault."""
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root
from alaya.vault import resolve_note_path
from alaya.zk import run_zk, ZKError


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


def get_note(relative_path: str, vault: Path) -> str:
    """Return the full content of a note by relative path."""
    path = resolve_note_path(relative_path, vault)
    if not path.exists():
        raise FileNotFoundError(f"Note not found: {relative_path}")
    return path.read_text()


def list_notes(
    vault: Path,
    directory: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> str:
    """Return a Markdown table of notes, optionally filtered by directory or tag."""
    args = ["list", "--format", "{{path}}\t{{title}}\t{{date}}\t{{tags}}", "--limit", str(limit)]
    if tag:
        args += ["--tag", tag]
    if directory:
        args.append(directory)

    raw = run_zk(args, vault)
    if not raw:
        return "No notes found."

    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        path = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else ""
        date = parts[2] if len(parts) > 2 else ""
        tags = parts[3] if len(parts) > 3 else ""
        rows.append(f"| [[{title}]] | `{path}` | {date} | {tags} |")

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
        parts = line.split("\t")
        path = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else path
        lines.append(f"- [[{title}]] (`{path}`)")

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
        parts = line.split("\t")
        path = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else path
        lines.append(f"- [[{title}]] (`{path}`)")

    return "\n".join(lines)


def get_tags(vault: Path) -> str:
    """Return a Markdown table of all tags in the vault with counts."""
    raw = run_zk(["tag", "list", "--format", "{{name}}\t{{note-count}}"], vault)
    if not raw:
        return "No tags found."

    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        name = parts[0] if len(parts) > 0 else ""
        count = parts[1] if len(parts) > 1 else "0"
        rows.append(f"| #{name} | {count} |")

    header = "| Tag | Notes |\n|---|---|"
    return header + "\n" + "\n".join(rows)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP) -> None:
    vault_root = get_vault_root

    @mcp.tool()
    def get_note_tool(path: str) -> str:
        """Read the full content of a note by its relative path (e.g. 'projects/second-brain.md')."""
        return get_note(path, vault_root())

    @mcp.tool()
    def list_notes_tool(directory: str = "", tag: str = "", limit: int = 50) -> str:
        """List notes in the vault, optionally filtered by directory or tag."""
        return list_notes(
            vault_root(),
            directory=directory or None,
            tag=tag or None,
            limit=limit,
        )

    @mcp.tool()
    def get_backlinks_tool(path: str) -> str:
        """Return all notes that link to the given note (backlinks)."""
        return get_backlinks(path, vault_root())

    @mcp.tool()
    def get_links_tool(path: str) -> str:
        """Return all notes that the given note links to (outgoing links)."""
        return get_links(path, vault_root())

    @mcp.tool()
    def get_tags_tool() -> str:
        """Return all tags in the vault with note counts."""
        return get_tags(vault_root())

    @mcp.tool()
    def reindex_vault_tool(confirm: bool = False) -> str:
        """Rebuild the full LanceDB vector index. Requires confirm=True."""
        return reindex_vault(vault_root(), confirm=confirm)


try:
    from alaya.server import mcp as _mcp
    _register(_mcp)
except ImportError:
    pass
