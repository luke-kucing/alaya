"""Late chunking: embed full document, then extract per-chunk embeddings.

Late chunking preserves cross-chunk context by running the full document
through the embedding model before splitting into chunks. Each chunk
embedding retains awareness of the surrounding document context.

This module provides late chunking for models that support it. When a model
doesn't support late chunking natively, the standard chunk-then-embed
approach is used automatically (see embedder.py).

Currently supports:
- jina-v3: via transformers library (token-level embeddings with mean pooling per chunk span)
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from alaya.index.embedder import Chunk
from alaya.index.models import get_active_model

logger = logging.getLogger(__name__)

_late_model: Any = None
_late_tokenizer: Any = None


def supports_late_chunking() -> bool:
    """Return True if the active embedding model supports late chunking."""
    return get_active_model().supports_late_chunking


def embed_chunks_late(full_text: str, chunks: list[Chunk]) -> list[np.ndarray] | None:
    """Embed chunks using late chunking: full doc → token embeddings → per-chunk pooling.

    Returns a list of embeddings (one per chunk), or None if late chunking
    is not available (caller should fall back to standard embedding).
    """
    cfg = get_active_model()
    if not cfg.supports_late_chunking:
        return None

    try:
        model, tokenizer = _load_late_model(cfg)
    except Exception as e:
        logger.warning("Failed to load late chunking model: %s", e)
        return None

    try:
        return _late_chunk_embed(full_text, chunks, model, tokenizer)
    except Exception as e:
        logger.warning("Late chunking failed, falling back to standard: %s", e)
        return None


def _load_late_model(cfg: Any) -> tuple[Any, Any]:
    """Load the transformers model and tokenizer for late chunking."""
    global _late_model, _late_tokenizer
    if _late_model is not None:
        return _late_model, _late_tokenizer

    import torch
    from transformers import AutoModel, AutoTokenizer

    logger.info("Loading late chunking model: %s", cfg.name)
    _late_tokenizer = AutoTokenizer.from_pretrained(cfg.name, trust_remote_code=True)
    _late_model = AutoModel.from_pretrained(cfg.name, trust_remote_code=True)
    _late_model.eval()
    logger.info("Late chunking model loaded")
    return _late_model, _late_tokenizer


def _late_chunk_embed(
    full_text: str,
    chunks: list[Chunk],
    model: Any,
    tokenizer: Any,
) -> list[np.ndarray]:
    """Run late chunking: encode full doc, find chunk spans, pool per span."""
    import torch

    # Tokenize the full document
    inputs = tokenizer(full_text, return_tensors="pt", truncation=True, max_length=8192)

    # Get token-level embeddings from the model
    with torch.no_grad():
        outputs = model(**inputs)
    token_embeddings = outputs.last_hidden_state[0]  # [seq_len, dim]

    # Find token spans for each chunk in the full text
    chunk_embeddings = []
    for chunk in chunks:
        # Find where this chunk's text appears in the full text
        start_char = full_text.find(chunk.text[:50])  # match first 50 chars
        if start_char == -1:
            # Fallback: use mean of all tokens
            emb = token_embeddings.mean(dim=0).numpy().astype(np.float32)
        else:
            end_char = start_char + len(chunk.text)
            # Map character offsets to token offsets
            start_token = _char_to_token(inputs, start_char)
            end_token = _char_to_token(inputs, end_char)
            if start_token is not None and end_token is not None:
                span = token_embeddings[start_token:end_token + 1]
                if span.shape[0] > 0:
                    emb = span.mean(dim=0).numpy().astype(np.float32)
                else:
                    emb = token_embeddings.mean(dim=0).numpy().astype(np.float32)
            else:
                emb = token_embeddings.mean(dim=0).numpy().astype(np.float32)

        # L2 normalize
        norm = np.linalg.norm(emb)
        if norm > 0:
            emb = emb / norm
        chunk_embeddings.append(emb)

    return chunk_embeddings


def _char_to_token(inputs: Any, char_offset: int) -> int | None:
    """Map a character offset to a token index using the tokenizer output."""
    try:
        return inputs.char_to_token(0, char_offset)
    except Exception:
        return None
