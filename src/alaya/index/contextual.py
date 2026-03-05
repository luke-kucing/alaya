"""Contextual retrieval: prepend chunk context at index time.

Inspired by Anthropic's contextual retrieval technique. Each chunk gets
a context prefix that situates it within its parent document, improving
retrieval accuracy by up to 49% (Anthropic benchmarks).

This implementation uses metadata-based context (no LLM call):
- Note title and directory for topical grounding
- Tags for semantic categorization
- Section header (if the chunk came from a section) for structural context
"""
from __future__ import annotations

from alaya.index.embedder import Chunk


def add_chunk_context(chunks: list[Chunk]) -> list[Chunk]:
    """Prepend contextual metadata to each chunk's text.

    The context prefix helps the embedding model understand what the chunk
    is about even when the chunk text alone is ambiguous. This is especially
    useful for chunks that begin mid-paragraph or reference things defined
    elsewhere in the note.
    """
    contextualized = []
    for chunk in chunks:
        prefix = _build_context_prefix(chunk)
        contextualized.append(Chunk(
            path=chunk.path,
            title=chunk.title,
            tags=chunk.tags,
            directory=chunk.directory,
            modified_date=chunk.modified_date,
            chunk_index=chunk.chunk_index,
            text=prefix + chunk.text,
        ))
    return contextualized


def _build_context_prefix(chunk: Chunk) -> str:
    """Build a context prefix from chunk metadata."""
    parts = []

    if chunk.title:
        parts.append(f"From note: {chunk.title}")

    if chunk.directory:
        parts.append(f"Directory: {chunk.directory}")

    if chunk.tags:
        parts.append(f"Tags: {', '.join(chunk.tags)}")

    # Extract section header if present at the start of the chunk
    lines = chunk.text.split("\n", 1)
    if lines and lines[0].startswith(("## ", "### ")):
        section = lines[0].lstrip("#").strip()
        parts.append(f"Section: {section}")

    if not parts:
        return ""

    return " | ".join(parts) + "\n\n"
