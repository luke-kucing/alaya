"""Embedder: chunk notes and embed with fastembed (model from registry)."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from alaya.index.models import get_active_model

logger = logging.getLogger(__name__)

_model = None
_loaded_model_name: str | None = None  # track which model is loaded
# Guards _model and _loaded_model_name against concurrent load by multiple threads
# (e.g. watcher ingest thread + write-through event handler).
_model_lock = threading.Lock()


def get_model():
    global _model, _loaded_model_name
    cfg = get_active_model()
    # Fast path: model already loaded and name matches — no lock needed for reads
    # since CPython's GIL makes these reads atomic, and model identity is stable.
    if _model is not None and _loaded_model_name == cfg.name:
        return _model, cfg
    # Slow path: load under lock to prevent concurrent double-initialisation.
    with _model_lock:
        # Re-check after acquiring the lock (double-checked locking pattern).
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


def reset_model() -> None:
    """Clear the cached model. Intended for use in tests only."""
    global _model, _loaded_model_name
    with _model_lock:
        _model = None
        _loaded_model_name = None


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


def embed_query(text: str) -> np.ndarray:
    """Embed a search query string. Returns a normalized float32 vector."""
    model, cfg = get_model()
    raw = np.array(list(model.query_embed([f"{cfg.search_prefix}{text}"])))
    norm = np.linalg.norm(raw[0])
    return (raw[0] / (norm if norm else 1)).astype(np.float32)


def embed_chunks(chunks: list[Chunk]) -> list[np.ndarray]:
    """Embed a list of chunks. Returns one normalized float32 ndarray per chunk."""
    model, cfg = get_model()
    texts = [f"{cfg.document_prefix}{c.text}" for c in chunks]
    raw = np.array(list(model.embed(texts)))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    normalized = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
    return [normalized[i] for i in range(len(chunks))]
