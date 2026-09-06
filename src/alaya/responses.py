"""Response shaping: token accounting and output caps.

An agent cannot budget a context window it can't measure, and any tool that
returns an unbounded blob — a long note, a wide search — can blow a local
model's window in a single call. So every response carries its token count, and
no response exceeds a configured cap unless the caller opts out.
"""
from __future__ import annotations

import logging
import os
import re

from alaya.tokens import count_tokens, truncate_to_tokens

logger = logging.getLogger(__name__)

DEFAULT_MAX_OUTPUT_TOKENS = 4000

_TOKEN_COMMENT = re.compile(r"<!--\s*token_count:\s*\d+.*?-->\s*$")

# Reserve room for the token_count comment and any truncation footer so the
# annotated response still fits under the cap.
_FOOTER_ALLOWANCE = 60


def get_max_output_tokens() -> int:
    """Cap on tool output in tokens. 0 (or negative) disables capping."""
    raw = os.environ.get("ALAYA_MAX_TOOL_OUTPUT_TOKENS")
    if raw is None:
        return DEFAULT_MAX_OUTPUT_TOKENS
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "Invalid ALAYA_MAX_TOOL_OUTPUT_TOKENS %r — using %d",
            raw, DEFAULT_MAX_OUTPUT_TOKENS,
        )
        return DEFAULT_MAX_OUTPUT_TOKENS


def has_token_count(text: str) -> bool:
    """True if *text* already ends with a token_count comment."""
    return bool(_TOKEN_COMMENT.search(text))


def annotate(text: str) -> str:
    """Append a token_count comment, unless one is already there."""
    if has_token_count(text):
        return text
    return f"{text}\n\n<!-- token_count: {count_tokens(text)} -->"


def cap(text: str, hint: str | None = None, budget: int | None = None) -> tuple[str, bool]:
    """Truncate *text* to the output cap. Returns ``(text, truncated)``.

    *hint* tells the caller how to retrieve the rest.
    """
    limit = get_max_output_tokens() if budget is None else budget
    if limit <= 0:
        return text, False

    total = count_tokens(text)
    room = limit - _FOOTER_ALLOWANCE
    if total <= limit or room <= 0:
        return text, False

    clipped, _ = truncate_to_tokens(text, room)
    dropped = total - count_tokens(clipped)
    footer = f"\n\n…[+{dropped} tokens truncated"
    footer += f"; {hint}]" if hint else "]"
    return clipped + footer, True


def shape(result, unbounded: bool = False, hint: str | None = None) -> str:
    """Cap and annotate a tool result. Non-string results pass through unchanged."""
    if not isinstance(result, str):
        return result
    text = result if unbounded else cap(result, hint)[0]
    return annotate(text)
