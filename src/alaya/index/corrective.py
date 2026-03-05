"""Corrective RAG: evaluate retrieval quality and retry with reformulated queries."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Minimum score for the top result to be considered "good enough"
_MIN_TOP_SCORE = 0.3

# Minimum number of results above threshold to skip correction
_MIN_GOOD_RESULTS = 1

# Score threshold for a result to be considered relevant
_RELEVANCE_THRESHOLD = 0.2


def needs_correction(results: list[dict], min_score: float = _MIN_TOP_SCORE) -> bool:
    """Return True if retrieval results are too low quality and should be retried."""
    if not results:
        return True
    top_score = results[0].get("score", 0.0)
    return top_score < min_score


def filter_relevant(results: list[dict], threshold: float = _RELEVANCE_THRESHOLD) -> list[dict]:
    """Remove results below the relevance threshold."""
    return [r for r in results if r.get("score", 0.0) >= threshold]


def reformulate_query(query: str) -> list[str]:
    """Generate alternative query formulations for retry.

    Uses simple heuristics (no LLM call):
    - Remove question words to get the core topic
    - Extract key noun phrases
    - Broaden by dropping qualifying words
    """
    alternatives = []

    # Strip question words to get the core content
    stripped = re.sub(
        r"^(what|when|where|who|why|how|which|can|does|did|is|are|was|were|should|could|would)\s+",
        "",
        query.strip(),
        flags=re.IGNORECASE,
    )
    stripped = re.sub(r"\?$", "", stripped).strip()
    if stripped and stripped.lower() != query.strip().lower():
        alternatives.append(stripped)

    # Drop common filler words to broaden the query
    filler = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "about", "my", "i", "me"}
    words = query.strip().split()
    core_words = [w for w in words if w.lower() not in filler]
    if len(core_words) >= 2 and " ".join(core_words).lower() != query.strip().lower():
        alternatives.append(" ".join(core_words))

    # If query is long, try just the last few meaningful words (often the topic)
    if len(core_words) > 4:
        alternatives.append(" ".join(core_words[-3:]))

    return alternatives
