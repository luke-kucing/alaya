"""Token counting and budget-aware truncation.

Uses tiktoken's cl100k encoding when available (install the ``tokenizer``
extra), and falls back to a word-based approximation otherwise. The fallback
deliberately over-estimates slightly: a budget that is respected by an
over-estimate is still respected by the real tokenizer.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_ENCODING = "cl100k_base"
_encoder = None
_encoder_tried = False


def _get_encoder():
    """Return a tiktoken encoder, or None if tiktoken is unavailable."""
    global _encoder, _encoder_tried
    if _encoder_tried:
        return _encoder
    _encoder_tried = True
    name = os.environ.get("ALAYA_TOKENIZER", _DEFAULT_ENCODING)
    try:
        import tiktoken
        _encoder = tiktoken.get_encoding(name)
    except Exception as e:
        logger.info("tiktoken unavailable (%s) — using word-based token approximation", e)
        _encoder = None
    return _encoder


def reset_encoder() -> None:
    """Clear the cached encoder. Intended for use in tests only."""
    global _encoder, _encoder_tried
    _encoder = None
    _encoder_tried = False


def count_tokens(text: str) -> int:
    """Return the token count for *text*."""
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    # Approximation: 1 word ~= 1.3 tokens, matching index.chunking._approx_tokens.
    return int(len(text.split()) * 1.3) + 1


def truncate_to_tokens(text: str, budget: int) -> tuple[str, bool]:
    """Truncate *text* to at most *budget* tokens.

    Returns ``(text, truncated)``. Truncation happens on a line boundary where
    one exists inside the budget, so Markdown structure survives.
    """
    if budget <= 0:
        return "", bool(text)
    if count_tokens(text) <= budget:
        return text, False

    enc = _get_encoder()
    if enc is not None:
        clipped = enc.decode(enc.encode(text, disallowed_special=())[:budget])
    else:
        # Word-based: invert the 1.3 ratio.
        words = text.split()
        clipped = " ".join(words[: max(1, int(budget / 1.3))])

    # Prefer a line boundary, but never drop more than the last third.
    newline = clipped.rfind("\n")
    if newline > len(clipped) * 2 // 3:
        clipped = clipped[:newline]
    return clipped.rstrip(), True
