"""Search tools: search_notes (M1: zk keyword fallback; M3: LanceDB hybrid)."""
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root
from alaya.zk import run_zk, ZKError


def _hybrid_search_available(vault: Path) -> bool:
    """Return True if a LanceDB index exists and has rows."""
    try:
        from alaya.index.store import get_store
        store = get_store(vault)
        return store.count() > 0
    except Exception:
        return False


def _run_hybrid_search(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    limit: int = 20,
) -> list[dict]:
    """Embed the query and run hybrid search against LanceDB."""
    from alaya.index.embedder import _get_model
    from alaya.index.store import get_store, hybrid_search

    model = _get_model()
    query_embedding = model.encode(
        [f"search_query: {query}"], normalize_embeddings=True
    )[0]

    store = get_store(vault)
    return hybrid_search(query, query_embedding, store, directory=directory, tags=tags, limit=limit)


def search_notes(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
) -> str:
    """Search notes by keyword or semantic query. Returns a Markdown table.

    Uses LanceDB hybrid search when an index is available; falls back to
    zk keyword search otherwise.
    """
    if _hybrid_search_available(vault):
        results = _run_hybrid_search(query, vault, directory=directory, tags=tags, limit=limit)
        if not results:
            return "No notes matching that query."
        rows = [
            f"| [[{r['title']}]] | `{r['path']}` | {r['score']:.2f} |"
            for r in results
        ]
        header = "| Title | Path | Score |\n|---|---|---|"
        return header + "\n" + "\n".join(rows)

    # fallback: zk keyword search
    args = [
        "list",
        "--match", query,
        "--format", "{{path}}\t{{title}}\t{{date}}",
        "--limit", str(limit),
    ]
    if directory:
        args.append(directory)
    if tags:
        for tag in tags:
            args += ["--tag", tag]
    if since:
        args += ["--modified-after", since]

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

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def search_notes_tool(
        query: str,
        directory: str = "",
        tags: list[str] | None = None,
        since: str = "",
        limit: int = 20,
    ) -> str:
        """Search notes by keyword or semantic query. Filter by directory, tags, or since date."""
        return search_notes(
            query,
            vault,
            directory=directory or None,
            tags=tags or None,
            since=since or None,
            limit=limit,
        )

