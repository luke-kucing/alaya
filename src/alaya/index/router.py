"""Adaptive query router: classify queries and route to the best retrieval strategy."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class QueryStrategy(Enum):
    KEYWORD = auto()     # short exact terms → FTS-only
    SEMANTIC = auto()    # natural language questions → vector-only
    HYBRID = auto()      # mixed → full hybrid (vector + FTS + RRF)
    TEMPORAL = auto()    # time-referenced queries → extract date filter + hybrid


@dataclass
class RoutedQuery:
    """Result of query classification."""
    strategy: QueryStrategy
    query: str
    since: str | None = None  # extracted date filter for TEMPORAL queries


# Patterns that indicate a natural language question
_QUESTION_PATTERNS = re.compile(
    r"^(what|when|where|who|why|how|which|can|does|did|is|are|was|were|should|could|would)\b",
    re.IGNORECASE,
)

# Patterns that indicate temporal references
_TEMPORAL_PATTERNS = [
    (re.compile(r"\b(today|this morning|this afternoon|tonight)\b", re.IGNORECASE), 0),
    (re.compile(r"\byesterday\b", re.IGNORECASE), 1),
    (re.compile(r"\blast\s+week\b", re.IGNORECASE), 7),
    (re.compile(r"\blast\s+month\b", re.IGNORECASE), 30),
    (re.compile(r"\bthis\s+week\b", re.IGNORECASE), 7),
    (re.compile(r"\bthis\s+month\b", re.IGNORECASE), 30),
    (re.compile(r"\brecently?\b", re.IGNORECASE), 14),
]

# ISO date pattern already in the query (e.g., "since 2026-01-15")
_ISO_DATE_PATTERN = re.compile(r"\bsince\s+(\d{4}-\d{2}-\d{2})\b", re.IGNORECASE)


def classify_query(query: str) -> RoutedQuery:
    """Classify a query and return the recommended retrieval strategy.

    The router uses simple heuristics rather than an ML classifier,
    keeping it fast and dependency-free.
    """
    stripped = query.strip()
    if not stripped:
        return RoutedQuery(strategy=QueryStrategy.HYBRID, query=stripped)

    # Check for explicit date in query ("since 2026-01-15")
    iso_match = _ISO_DATE_PATTERN.search(stripped)
    if iso_match:
        clean_query = _ISO_DATE_PATTERN.sub("", stripped).strip()
        return RoutedQuery(
            strategy=QueryStrategy.TEMPORAL,
            query=clean_query or stripped,
            since=iso_match.group(1),
        )

    # Check for temporal references
    for pattern, days_back in _TEMPORAL_PATTERNS:
        if pattern.search(stripped):
            from datetime import date, timedelta
            since_date = (date.today() - timedelta(days=days_back)).isoformat()
            return RoutedQuery(
                strategy=QueryStrategy.TEMPORAL,
                query=stripped,
                since=since_date,
            )

    words = stripped.split()

    # Short queries (1-2 words, no question words) → keyword search
    if len(words) <= 2 and not _QUESTION_PATTERNS.match(stripped):
        return RoutedQuery(strategy=QueryStrategy.KEYWORD, query=stripped)

    # Questions → semantic search (better at matching intent)
    if _QUESTION_PATTERNS.match(stripped):
        return RoutedQuery(strategy=QueryStrategy.SEMANTIC, query=stripped)

    # Default: hybrid
    return RoutedQuery(strategy=QueryStrategy.HYBRID, query=stripped)
