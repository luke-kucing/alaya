"""Search tools: search_notes (M1: zk keyword fallback; M3: LanceDB hybrid)."""
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root
from alaya.zk import run_zk, ZKError


def search_notes(
    query: str,
    vault: Path,
    directory: str | None = None,
    limit: int = 20,
) -> str:
    """Search notes by keyword using zk. Returns a Markdown table of results."""
    args = [
        "list",
        "--match", query,
        "--format", "{{path}}\t{{title}}\t{{date}}",
        "--limit", str(limit),
    ]
    if directory:
        args.append(directory)

    try:
        raw = run_zk(args, vault)
    except ZKError:
        return "No results found."

    if not raw:
        return "No notes matching that query."

    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        path = parts[0] if len(parts) > 0 else ""
        title = parts[1] if len(parts) > 1 else ""
        date = parts[2] if len(parts) > 2 else ""
        rows.append(f"| [[{title}]] | `{path}` | {date} |")

    header = "| Title | Path | Date |\n|---|---|---|"
    return header + "\n" + "\n".join(rows)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP) -> None:
    vault_root = get_vault_root

    @mcp.tool()
    def search_notes_tool(query: str, directory: str = "", limit: int = 20) -> str:
        """Search notes by keyword. Optionally restrict to a directory."""
        return search_notes(query, vault_root(), directory=directory or None, limit=limit)


try:
    from alaya.server import mcp as _mcp
    _register(_mcp)
except ImportError:
    pass
