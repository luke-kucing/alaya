"""Enrichment tools: LLM-powered chunk enhancement for better retrieval.

These tools let the MCP client (the LLM agent) enhance the index by providing
generated content — contextual summaries, propositions, hierarchical summaries.
The server stores the enrichments; the agent generates the content.
"""
import logging
from pathlib import Path

import numpy as np

from fastmcp import FastMCP
from alaya.errors import error, INVALID_ARGUMENT

logger = logging.getLogger(__name__)


def enrich_chunk_context(
    path: str,
    chunk_index: int,
    context: str,
    vault: Path,
) -> str:
    """Store LLM-generated context for a specific chunk.

    The agent reads a chunk (via get_note + search), generates a brief context
    summary explaining what the chunk is about within the full document, and
    passes it here. The chunk's text is updated to prepend the context.

    This is the LLM-powered version of contextual retrieval (vs. the metadata-
    based version that runs automatically at index time).
    """
    from alaya.index.store import get_store, _sq, _STORE_ERRORS
    from alaya.index.embedder import embed_chunks, Chunk

    store = get_store(vault)
    table = store._get_table()

    try:
        rows = table.search().where(
            f"path = '{_sq(path)}' AND chunk_index = {int(chunk_index)}"
        ).limit(1).to_list()

        if not rows:
            return error(INVALID_ARGUMENT, f"Chunk not found: {path} index {chunk_index}")

        row = dict(rows[0])
        original_text = row["text"]

        # Prepend LLM context to the chunk text
        enriched_text = f"[Context: {context}]\n\n{original_text}"

        # Re-embed with the enriched text
        chunk = Chunk(
            path=row["path"],
            title=row["title"],
            tags=row.get("tags", "").strip(",").split(",") if row.get("tags") else [],
            directory=row["directory"],
            modified_date=row["modified_date"],
            chunk_index=row["chunk_index"],
            text=enriched_text,
        )
        embeddings = embed_chunks([chunk])

        # Update the row in-place
        row.pop("_distance", None)
        row.pop("_relevance_score", None)
        row["text"] = enriched_text
        row["vector"] = embeddings[0].tolist()

        table.delete(f"path = '{_sq(path)}' AND chunk_index = {int(chunk_index)}")
        table.add([row])

        return f"Enriched chunk {chunk_index} of `{path}` with context."

    except _STORE_ERRORS as e:
        return error(INVALID_ARGUMENT, f"Failed to enrich chunk: {e}")


def store_propositions(
    path: str,
    propositions: list[str],
    vault: Path,
) -> str:
    """Store atomic propositions extracted from a note.

    The agent reads a note, decomposes it into atomic factual statements
    ("X is Y", "A causes B"), and passes them here. Each proposition is
    stored as a separate chunk in the index for fine-grained retrieval.

    Propositions are stored with a special chunk_index range (1000+) to
    distinguish them from regular chunks.
    """
    from alaya.index.store import get_store, upsert_note, _sq, _STORE_ERRORS
    from alaya.index.embedder import embed_chunks, Chunk

    if not propositions:
        return error(INVALID_ARGUMENT, "No propositions provided.")

    store = get_store(vault)
    table = store._get_table()

    # Get metadata from existing chunks for this path
    try:
        existing = table.search().where(f"path = '{_sq(path)}'").limit(1).to_list()
    except _STORE_ERRORS:
        existing = []

    title = existing[0]["title"] if existing else Path(path).stem
    directory = existing[0]["directory"] if existing else ""
    tags_str = existing[0].get("tags", "") if existing else ""
    tags = [t for t in tags_str.strip(",").split(",") if t]
    date = existing[0].get("modified_date", "") if existing else ""

    # Delete any existing propositions for this path
    try:
        table.delete(f"path = '{_sq(path)}' AND chunk_index >= 1000")
    except _STORE_ERRORS:
        pass

    # Create proposition chunks
    chunks = [
        Chunk(
            path=path,
            title=title,
            tags=tags,
            directory=directory,
            modified_date=date,
            chunk_index=1000 + i,
            text=f"[Proposition from {title}] {prop}",
        )
        for i, prop in enumerate(propositions)
    ]

    embeddings = embed_chunks(chunks)

    # Add to index (don't use upsert_note — that would delete regular chunks)
    from alaya.index.models import get_active_model
    active_model = get_active_model().key
    has_model_col = "embedding_model" in {f.name for f in table.schema}

    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        row = {
            "path": chunk.path,
            "title": chunk.title,
            "directory": chunk.directory,
            "tags": "," + ",".join(chunk.tags) + "," if chunk.tags else "",
            "modified_date": chunk.modified_date,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "vector": embedding.tolist(),
        }
        if has_model_col:
            row["embedding_model"] = active_model
        rows.append(row)

    try:
        table.add(rows)
    except _STORE_ERRORS as e:
        return error(INVALID_ARGUMENT, f"Failed to store propositions: {e}")

    return f"Stored {len(propositions)} propositions for `{path}`."


def store_summary(
    paths: list[str],
    summary: str,
    summary_title: str,
    vault: Path,
) -> str:
    """Store a hierarchical summary (RAPTOR) covering multiple notes.

    The agent reads several related notes, generates a summary that captures
    the high-level themes, and passes it here. The summary is stored as a
    synthetic chunk in the index, enabling retrieval of broad topics that
    span multiple notes.

    Summaries are stored under a synthetic path `_summaries/<title>.md`.
    """
    from alaya.index.store import get_store, _sq, _STORE_ERRORS
    from alaya.index.embedder import embed_chunks, Chunk
    from alaya.index.models import get_active_model

    if not summary.strip():
        return error(INVALID_ARGUMENT, "Empty summary.")

    store = get_store(vault)
    table = store._get_table()

    synthetic_path = f"_summaries/{_slugify(summary_title)}.md"

    # Delete existing summary at this path
    try:
        table.delete(f"path = '{_sq(synthetic_path)}'")
    except _STORE_ERRORS:
        pass

    # Build context with source note references
    source_refs = ", ".join(f"[[{Path(p).stem}]]" for p in paths)
    full_text = f"[Summary of: {source_refs}]\n\n{summary}"

    chunk = Chunk(
        path=synthetic_path,
        title=summary_title,
        tags=["_summary"],
        directory="_summaries",
        modified_date="",
        chunk_index=0,
        text=full_text,
    )

    embeddings = embed_chunks([chunk])

    active_model = get_active_model().key
    has_model_col = "embedding_model" in {f.name for f in table.schema}

    row = {
        "path": synthetic_path,
        "title": summary_title,
        "directory": "_summaries",
        "tags": ",_summary,",
        "modified_date": "",
        "chunk_index": 0,
        "text": full_text,
        "vector": embeddings[0].tolist(),
    }
    if has_model_col:
        row["embedding_model"] = active_model

    try:
        table.add([row])
    except _STORE_ERRORS as e:
        return error(INVALID_ARGUMENT, f"Failed to store summary: {e}")

    return f"Stored summary `{summary_title}` covering {len(paths)} notes."


def _slugify(text: str) -> str:
    """Simple slug: lowercase, replace spaces with hyphens, drop non-alnum."""
    import re
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[\s_]+", "-", slug).strip("-")


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def enrich_chunk_context_tool(
        path: str,
        chunk_index: int,
        context: str,
    ) -> str:
        """Enrich a specific chunk with LLM-generated context for better retrieval.

        Read the chunk first (via search or get_note), then write a brief context
        summary explaining what this chunk covers within the full document. The
        chunk will be re-embedded with the context prepended.

        path: the note's relative path
        chunk_index: the chunk number (from search results)
        context: a 1-2 sentence description of what this chunk covers
        """
        return enrich_chunk_context(path, chunk_index, context, vault)

    @mcp.tool()
    def store_propositions_tool(
        path: str,
        propositions: list[str],
    ) -> str:
        """Store atomic factual propositions extracted from a note.

        Read a note, decompose it into atomic statements like "X is Y" or
        "A causes B", and pass the list here. Each proposition is stored as
        a separate searchable entry in the index for fine-grained retrieval.

        path: the note's relative path
        propositions: list of atomic factual statements
        """
        return store_propositions(path, propositions, vault)

    @mcp.tool()
    def store_summary_tool(
        paths: list[str],
        summary: str,
        summary_title: str,
    ) -> str:
        """Store a hierarchical summary (RAPTOR) covering multiple related notes.

        Read several related notes, write a summary capturing high-level themes,
        and pass it here. The summary becomes searchable, enabling retrieval of
        broad topics that span multiple notes.

        paths: list of source note paths this summary covers
        summary: the generated summary text
        summary_title: a descriptive title for the summary
        """
        return store_summary(paths, summary, summary_title, vault)
