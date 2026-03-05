"""Search tools: search_notes with adaptive query routing."""
import logging
from pathlib import Path

from fastmcp import FastMCP

logger = logging.getLogger(__name__)


_hybrid_available_cache: bool | None = None


def _hybrid_search_available(vault: Path) -> bool:
    """Return True if a LanceDB index exists and has rows.

    Result is cached after the first True to avoid repeated store lookups.
    """
    global _hybrid_available_cache
    if _hybrid_available_cache:
        return True
    try:
        from alaya.index.store import get_store
        store = get_store(vault)
        result = store.count() > 0
        if result:
            _hybrid_available_cache = True
        return result
    except Exception:
        return False


def _run_routed_search(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
    rerank: bool = False,
    hyde: bool = False,
) -> list[dict]:
    """Route the query to the best search strategy, then execute."""
    from alaya.index.router import classify_query, QueryStrategy
    from alaya.index.embedder import embed_query
    from alaya.index.store import get_store, hybrid_search, keyword_search

    routed = classify_query(query)
    logger.debug("Query routed: strategy=%s query=%r since=%s", routed.strategy.name, routed.query, routed.since)

    # Merge router-extracted date filter with explicit since parameter
    effective_since = since or routed.since
    store = get_store(vault)

    if routed.strategy == QueryStrategy.KEYWORD:
        results = keyword_search(
            routed.query, store,
            directory=directory, tags=tags, since=effective_since, limit=limit,
        )
        # Fall through to hybrid if keyword search returns nothing
        if results:
            return results

    # For SEMANTIC, HYBRID, TEMPORAL, or KEYWORD fallthrough: use hybrid search
    if hyde and routed.strategy == QueryStrategy.SEMANTIC:
        from alaya.index.hyde import embed_with_hyde
        query_embedding = embed_with_hyde(routed.query)
    else:
        query_embedding = embed_query(routed.query)

    return hybrid_search(
        routed.query, query_embedding, store,
        directory=directory, tags=tags, since=effective_since, limit=limit, rerank=rerank,
    )


def _run_corrective_search(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
    rerank: bool = False,
    hyde: bool = False,
) -> list[dict]:
    """Search with corrective RAG: retry with reformulated queries if results are poor."""
    from alaya.index.corrective import needs_correction, filter_relevant, reformulate_query

    results = _run_routed_search(
        query, vault, directory=directory, tags=tags, since=since, limit=limit, rerank=rerank, hyde=hyde,
    )

    # Filter out irrelevant results
    results = filter_relevant(results)

    # If results are good enough, return them
    if not needs_correction(results):
        return results

    # Try reformulated queries
    for alt_query in reformulate_query(query):
        logger.debug("Corrective RAG retry with: %r", alt_query)
        alt_results = _run_routed_search(
            alt_query, vault, directory=directory, tags=tags, since=since, limit=limit, rerank=rerank, hyde=hyde,
        )
        alt_results = filter_relevant(alt_results)
        if not needs_correction(alt_results):
            return alt_results
        # Merge: keep the best results seen so far
        if alt_results and (not results or alt_results[0]["score"] > results[0]["score"]):
            results = alt_results

    return results


def _run_hybrid_search(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
    rerank: bool = False,
) -> list[dict]:
    """Embed the query and run hybrid search against LanceDB.

    This is the non-routed path, used by callers that bypass routing
    (e.g., smart_capture's _find_matching_note).
    """
    from alaya.index.embedder import embed_query
    from alaya.index.store import get_store, hybrid_search

    query_embedding = embed_query(query)
    store = get_store(vault)
    return hybrid_search(
        query, query_embedding, store,
        directory=directory, tags=tags, since=since, limit=limit, rerank=rerank,
    )


def search_notes(
    query: str,
    vault: Path,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 20,
    rerank: bool = False,
    graph_expand: bool = False,
    hyde: bool = False,
    backend=None,
    cache=None,
) -> str:
    """Search notes by keyword or semantic query. Returns a Markdown table.

    Uses adaptive query routing when an index is available; falls back to
    backend keyword search otherwise.
    """
    if _hybrid_search_available(vault):
        results = _run_corrective_search(
            query, vault, directory=directory, tags=tags, since=since, limit=limit, rerank=rerank, hyde=hyde,
        )
        if graph_expand and results:
            from alaya.index.graph_rag import expand_with_graph
            results = expand_with_graph(results, vault, cache=cache)[:limit]
        if not results:
            return "No notes matching that query."
        rows = [
            f"| [[{r['title']}]] | `{r['path']}` | {r['score']:.2f} |"
            for r in results
        ]
        header = "| Title | Path | Score |\n|---|---|---|"
        return header + "\n" + "\n".join(rows)

    # Fallback: backend keyword search or zk CLI
    if backend:
        entries = backend.keyword_search(query, directory=directory, tags=tags, since=since, limit=limit)
        if not entries:
            return "No notes matching that query."
        rows = [f"| [[{e.title}]] | `{e.path}` | {e.date} |" for e in entries]
        header = "| Title | Path | Date |\n|---|---|---|"
        return header + "\n" + "\n".join(rows)

    # Legacy zk CLI fallback
    from alaya.zk import run_zk, ZKError, _reject_flag
    args = [
        "list",
        "--match", query,
        "--format", "{{path}}\t{{title}}\t{{format-date created '%Y-%m-%d'}}",
        "--limit", str(limit),
    ]
    if directory:
        args += ["--", _reject_flag(directory, "directory")]
    if tags:
        for tag in tags:
            args += ["--tag", _reject_flag(tag, "tag")]
    if since:
        args += ["--modified-after", _reject_flag(since, "since")]

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

def _register(mcp: FastMCP, vault: Path, backend=None, cache=None) -> None:
    @mcp.tool()
    def search_notes_tool(
        query: str,
        directory: str = "",
        tags: list[str] | None = None,
        since: str = "",
        limit: int = 20,
        rerank: bool = False,
        graph_expand: bool = False,
        hyde: bool = False,
    ) -> str:
        """Search notes by keyword or semantic query. Filter by directory, tags, or since date.

        Automatically routes queries to the best strategy:
        - Short exact terms use keyword (BM25) search
        - Questions use semantic (vector) search
        - Time-referenced queries extract date filters automatically
        - Mixed queries use full hybrid (vector + BM25 + RRF)

        Set rerank=True for higher precision (uses cross-encoder, adds latency).
        Set graph_expand=True to include wikilink-connected notes in results.
        Set hyde=True for semantic queries to embed a hypothetical answer
        instead of the raw query (bridges vocabulary gaps).
        """
        return search_notes(
            query,
            vault,
            directory=directory or None,
            tags=tags or None,
            since=since or None,
            limit=limit,
            rerank=rerank,
            graph_expand=graph_expand,
            hyde=hyde,
            backend=backend,
            cache=cache,
        )
