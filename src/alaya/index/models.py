"""Embedding model registry for alaya."""
from __future__ import annotations

import dataclasses
import functools
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingModelConfig:
    key: str  # unique registry key used for identity comparisons
    name: str  # HuggingFace model name passed to fastembed
    file_name: str | None
    dimensions: int
    search_prefix: str
    document_prefix: str
    supports_late_chunking: bool = False  # model supports contextual chunk embeddings
    backend: str = "fastembed"  # or "openai": an OpenAI-compatible /embeddings endpoint (#159)
    url: str | None = None  # endpoint base URL when backend == "openai"


MODELS: dict[str, EmbeddingModelConfig] = {
    "nomic-v1.5": EmbeddingModelConfig(
        key="nomic-v1.5",
        name="nomic-ai/nomic-embed-text-v1.5",
        file_name=None,  # fastembed default (model.onnx)
        dimensions=768,
        search_prefix="search_query: ",
        document_prefix="search_document: ",
    ),
    "nomic-v1.5-q4": EmbeddingModelConfig(
        key="nomic-v1.5-q4",
        name="nomic-ai/nomic-embed-text-v1.5",
        file_name="onnx/model_q4.onnx",
        dimensions=768,
        search_prefix="search_query: ",
        document_prefix="search_document: ",
    ),
    "jina-v3": EmbeddingModelConfig(
        key="jina-v3",
        name="jinaai/jina-embeddings-v3",
        file_name=None,
        dimensions=1024,
        search_prefix="",
        document_prefix="",
        supports_late_chunking=True,
    ),
}

DEFAULT_MODEL_KEY = "nomic-v1.5"


def get_active_model() -> EmbeddingModelConfig:
    """Return the active model config from ALAYA_EMBEDDING_MODEL env var, or the default.

    With ALAYA_EMBEDDING_URL set, embeddings come from that OpenAI-compatible endpoint instead.
    The registry entry still supplies prefixes and dims; ALAYA_EMBEDDING_REMOTE_MODEL names the
    served model (default: the entry's HuggingFace name).
    """
    key = os.environ.get("ALAYA_EMBEDDING_MODEL", DEFAULT_MODEL_KEY)
    if key not in MODELS:
        raise ValueError(f"Unknown embedding model {key!r}. Available: {sorted(MODELS)}")
    cfg = MODELS[key]
    url = os.environ.get("ALAYA_EMBEDDING_URL")
    if not url:
        return cfg
    return _resolve_remote(cfg, url.rstrip("/"), os.environ.get("ALAYA_EMBEDDING_REMOTE_MODEL", cfg.name))


@functools.lru_cache(maxsize=None)
def _resolve_remote(cfg: EmbeddingModelConfig, url: str, model: str) -> EmbeddingModelConfig:
    """Probe the endpoint once per process; fall back to local *cfg* if it is down or mismatched."""
    from alaya.index.remote_embedder import RemoteEmbedding
    try:
        dims = len(next(RemoteEmbedding(url, model).embed([f"{cfg.document_prefix}ping"])))
    except Exception as e:  # any failure: keep serving on the local model
        logger.warning("Embedding endpoint %s unavailable (%s); using local %s", url, e, cfg.key)
        return cfg
    if dims != cfg.dimensions:
        logger.warning("Endpoint %s model %s returns %d dims, %s expects %d; using local %s",
                       url, model, dims, cfg.key, cfg.dimensions, cfg.key)
        return cfg
    # A distinct key, so switching backend triggers the background re-embed (#78).
    return dataclasses.replace(cfg, key=f"openai:{model}", name=model, file_name=None,
                               supports_late_chunking=False, backend="openai", url=url)
