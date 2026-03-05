"""Embedder: chunk notes and embed with fastembed (model from registry)."""
from __future__ import annotations

import functools
import logging
import threading
from dataclasses import dataclass

import numpy as np

from alaya.index.models import get_active_model

logger = logging.getLogger(__name__)

_model = None
_loaded_model_key: str | None = None  # track which model variant is loaded
# Guards _model and _loaded_model_key against concurrent load by multiple threads
# (e.g. watcher ingest thread + write-through event handler).
_model_lock = threading.Lock()


def get_model():
    global _model, _loaded_model_key
    cfg = get_active_model()
    # Fast path: model already loaded and key matches — no lock needed for reads
    # since CPython's GIL makes these reads atomic, and model identity is stable.
    if _model is not None and _loaded_model_key == cfg.key:
        return _model, cfg
    # Slow path: load under lock to prevent concurrent double-initialisation.
    with _model_lock:
        # Re-check after acquiring the lock (double-checked locking pattern).
        if _model is None or _loaded_model_key != cfg.key:
            logger.info("Loading embedding model: %s (%s)", cfg.key, cfg.name)
            from fastembed import TextEmbedding
            kwargs = {}
            if cfg.file_name:
                kwargs["model_file"] = cfg.file_name
            _model = TextEmbedding(cfg.name, **kwargs)
            _loaded_model_key = cfg.key
            logger.info("Embedding model loaded")
    return _model, cfg


def reset_model() -> None:
    """Clear the cached model. Intended for use in tests only."""
    global _model, _loaded_model_key, _embed_query_cache_key, _embed_query_cached
    with _model_lock:
        _model = None
        _loaded_model_key = None
    _embed_query_cache_key = None
    _embed_query_cached = None


@dataclass
class Chunk:
    path: str
    title: str
    tags: list[str]
    directory: str
    modified_date: str
    chunk_index: int
    text: str


def chunk_note(path: str, content: str, contextual: bool = True) -> list[Chunk]:
    """Split a note into chunks using the appropriate strategy for its content.

    When contextual=True (default), prepends metadata context to each chunk
    for improved retrieval accuracy (contextual retrieval technique).
    """
    from alaya.index.chunking import select_strategy, ChunkConfig
    strategy = select_strategy(path, content)
    chunks = strategy.chunk(path, content, ChunkConfig())

    if contextual:
        from alaya.index.contextual import add_chunk_context
        chunks = add_chunk_context(chunks)

    return chunks


_embed_query_cache_key: str | None = None
_embed_query_cached = None


def _make_embed_query_cache():
    """Create a new LRU-cached embed function bound to the current model."""
    @functools.lru_cache(maxsize=128)
    def _cached_embed(text: str) -> bytes:
        model, cfg = get_model()
        raw = np.array(list(model.query_embed([f"{cfg.search_prefix}{text}"])))
        norm = np.linalg.norm(raw[0])
        vec = (raw[0] / (norm if norm else 1)).astype(np.float32)
        return vec.tobytes()
    return _cached_embed


def embed_query(text: str) -> np.ndarray:
    """Embed a search query string. Returns a normalized float32 vector.

    Results are LRU-cached (up to 128 entries) per model key to avoid
    redundant CPU inference for repeated queries.
    """
    global _embed_query_cache_key, _embed_query_cached
    cfg = get_active_model()
    if _embed_query_cached is None or _embed_query_cache_key != cfg.key:
        _embed_query_cached = _make_embed_query_cache()
        _embed_query_cache_key = cfg.key
    raw_bytes = _embed_query_cached(text)
    return np.frombuffer(raw_bytes, dtype=np.float32).copy()


def embed_chunks(chunks: list[Chunk], full_text: str | None = None) -> list[np.ndarray]:
    """Embed a list of chunks. Returns one normalized float32 ndarray per chunk.

    When full_text is provided and the active model supports late chunking,
    uses late chunking (full doc -> token embeddings -> per-chunk pooling)
    for better cross-chunk context preservation.
    """
    # Try late chunking if full document text is available
    if full_text is not None:
        from alaya.index.late_chunking import supports_late_chunking, embed_chunks_late
        if supports_late_chunking():
            result = embed_chunks_late(full_text, chunks)
            if result is not None:
                return result

    # Standard chunk-then-embed approach
    model, cfg = get_model()
    texts = [f"{cfg.document_prefix}{c.text}" for c in chunks]
    raw = np.array(list(model.embed(texts)))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    normalized = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
    return [normalized[i] for i in range(len(chunks))]
