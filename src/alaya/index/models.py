"""Embedding model registry for alaya."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingModelConfig:
    name: str
    file_name: str | None
    dimensions: int
    search_prefix: str
    document_prefix: str


MODELS: dict[str, EmbeddingModelConfig] = {
    "nomic-v1.5": EmbeddingModelConfig(
        name="nomic-ai/nomic-embed-text-v1.5",
        file_name=None,  # fastembed default (model.onnx)
        dimensions=768,
        search_prefix="search_query: ",
        document_prefix="search_document: ",
    ),
    "nomic-v1.5-q4": EmbeddingModelConfig(
        name="nomic-ai/nomic-embed-text-v1.5",
        file_name="onnx/model_q4.onnx",
        dimensions=768,
        search_prefix="search_query: ",
        document_prefix="search_document: ",
    ),
}

DEFAULT_MODEL_KEY = "nomic-v1.5"


def get_active_model() -> EmbeddingModelConfig:
    """Return the active model config from ALAYA_EMBEDDING_MODEL env var, or the default."""
    key = os.environ.get("ALAYA_EMBEDDING_MODEL", DEFAULT_MODEL_KEY)
    if key not in MODELS:
        raise ValueError(f"Unknown embedding model {key!r}. Available: {sorted(MODELS)}")
    return MODELS[key]
