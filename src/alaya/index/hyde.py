"""HyDE: Hypothetical Document Embeddings for search.

Generates a hypothetical answer document from a query, then embeds the
hypothetical document instead of the raw query. This bridges the vocabulary
gap between questions and stored notes.

Supports two modes:
- Template-based (default, no LLM needed): expands the query into a
  document-like format using simple templates
- LLM-based (optional): uses an LLM to generate a hypothetical answer
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def generate_hypothetical_document(query: str) -> str:
    """Generate a hypothetical document that might answer the query.

    Uses template-based expansion (no LLM). The idea is to make the query
    look more like a document chunk so the embedding is closer to relevant
    stored content in vector space.
    """
    stripped = query.strip().rstrip("?").strip()

    # Expand questions into statement form
    lower = stripped.lower()

    if lower.startswith(("what is ", "what are ")):
        topic = stripped.split(maxsplit=2)[-1]
        return (
            f"{topic}\n\n"
            f"{topic} is a concept or entity in the knowledge base. "
            f"This note covers the key aspects, definitions, and relationships of {topic}. "
            f"Related topics and references are linked throughout."
        )

    if lower.startswith("how to ") or lower.startswith("how do "):
        task = stripped.split(maxsplit=2)[-1]
        return (
            f"How to {task}\n\n"
            f"This note describes the process and steps for {task}. "
            f"It covers prerequisites, implementation details, and common patterns. "
            f"See related notes for additional context."
        )

    if lower.startswith(("why ", "when ", "where ", "who ")):
        return (
            f"{stripped}\n\n"
            f"This note addresses: {stripped}. "
            f"It provides context, reasoning, and supporting details. "
            f"Related notes are linked for further reading."
        )

    # Default: wrap the query in a document-like context
    return (
        f"{stripped}\n\n"
        f"This note covers {stripped}. "
        f"Key points, details, and related concepts are documented below. "
        f"See linked notes for additional context and related topics."
    )


def embed_with_hyde(query: str) -> np.ndarray:
    """Embed a query using HyDE: generate hypothetical doc, then embed it.

    Returns the embedding of the hypothetical document, which should be
    closer in vector space to relevant stored chunks than the raw query.
    """
    from alaya.index.embedder import embed_query

    hypothetical_doc = generate_hypothetical_document(query)
    logger.debug("HyDE hypothetical document: %s", hypothetical_doc[:100])
    return embed_query(hypothetical_doc)
