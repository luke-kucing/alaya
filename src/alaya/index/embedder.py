"""Embedder: chunk notes by section, embed with nomic-embed-text-v1.5 (fastembed)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
_model = None  # lazy-loaded singleton


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME)
        logger.info("Embedding model loaded")
    return _model


@dataclass
class Chunk:
    path: str
    title: str
    tags: list[str]
    directory: str
    modified_date: str
    chunk_index: int
    text: str


def chunk_note(path: str, content: str) -> list[Chunk]:
    """Split a note into chunks using the appropriate strategy for its content."""
    from alaya.index.chunking import select_strategy, ChunkConfig
    strategy = select_strategy(path, content)
    return strategy.chunk(path, content, ChunkConfig())


def embed_chunks(chunks: list[Chunk]) -> list[np.ndarray]:
    """Embed a list of chunks. Returns one normalized float32 ndarray per chunk."""
    model = _get_model()
    # nomic-embed requires a task prefix; "search_document:" for indexed content
    texts = [f"search_document: {c.text}" for c in chunks]
    raw = np.array(list(model.embed(texts)))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    normalized = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
    return [normalized[i] for i in range(len(chunks))]
