"""Embedder: chunk notes and embed with fastembed (model from registry)."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from alaya.index.models import get_active_model

logger = logging.getLogger(__name__)

_model = None
_loaded_model_name: str | None = None  # track which model is loaded


def get_model():
    global _model, _loaded_model_name
    cfg = get_active_model()
    if _model is None or _loaded_model_name != cfg.name:
        logger.info("Loading embedding model: %s", cfg.name)
        from fastembed import TextEmbedding
        kwargs = {}
        if cfg.file_name:
            kwargs["model_file"] = cfg.file_name
        _model = TextEmbedding(cfg.name, **kwargs)
        _loaded_model_name = cfg.name
        logger.info("Embedding model loaded")
    return _model, cfg


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
    model, cfg = get_model()
    texts = [f"{cfg.document_prefix}{c.text}" for c in chunks]
    raw = np.array(list(model.embed(texts)))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    normalized = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
    return [normalized[i] for i in range(len(chunks))]
