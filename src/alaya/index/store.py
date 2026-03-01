"""LanceDB store: upsert_note, delete_note_from_index, hybrid_search."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

logger = logging.getLogger(__name__)

_TABLE_NAME = "notes"
# LanceDB raises OSError (disk/connection), ValueError (bad query),
# and pa.ArrowInvalid (schema mismatch). We catch these specifically
# so programming errors (TypeError, KeyError, etc.) still propagate.
_STORE_ERRORS = (OSError, ValueError, pa.ArrowInvalid)


def _get_dim() -> int:
    from alaya.index.models import get_active_model
    return get_active_model().dimensions


def _sq(value: str) -> str:
    """Escape a string for safe interpolation into a LanceDB SQL filter expression.

    LanceDB does not support parameterized queries, so we centralise escaping here.
    Standard SQL single-quote doubling is the correct approach; this helper ensures
    it is applied consistently rather than inline at each callsite.
    """
    return value.replace("'", "''")


def _sq_like(value: str) -> str:
    """Escape a string for use inside a SQL LIKE pattern.

    Escapes single quotes (SQL string delimiter) and LIKE wildcards
    (% = any sequence, _ = any single character) so the value is matched
    literally rather than as a pattern.
    """
    escaped = value.replace("'", "''")
    escaped = escaped.replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return escaped


@dataclass
class VaultStore:
    """Thin wrapper around a LanceDB table for the vault index."""
    db_path: Path
    _db: Any = None
    _table: Any = None

    def _connect(self) -> Any:
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    def _get_table(self) -> Any:
        if self._table is None:
            db = self._connect()
            schema = pa.schema([
                pa.field("path", pa.string()),
                pa.field("title", pa.string()),
                pa.field("directory", pa.string()),
                pa.field("tags", pa.string()),  # comma-separated
                pa.field("modified_date", pa.string()),
                pa.field("chunk_index", pa.int32()),
                pa.field("text", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), _get_dim())),
                pa.field("embedding_model", pa.string()),
            ])
            try:
                self._table = db.create_table(_TABLE_NAME, schema=schema, exist_ok=True)
            except (pa.ArrowInvalid, Exception):
                # Existing table has old schema (no embedding_model column).
                # Open it as-is — search still works, model tracking is degraded.
                self._table = db.open_table(_TABLE_NAME)
        return self._table

    def count(self) -> int:
        try:
            return self._get_table().count_rows()
        except _STORE_ERRORS:
            return 0


def get_index_model(store: VaultStore) -> str | None:
    """Return the embedding model name stored in the index, or None if index is empty/old schema."""
    try:
        table = store._get_table()
        if "embedding_model" not in {f.name for f in table.schema}:
            return None  # old schema, no model tracking
        rows = table.search().limit(1).to_list()
        if rows:
            return rows[0].get("embedding_model") or None
    except _STORE_ERRORS:
        pass
    return None


def upsert_note(
    path: str,
    chunks: list,
    embeddings: list[np.ndarray],
    store: VaultStore,
) -> None:
    """Replace all chunks for `path` with the new chunks + embeddings."""
    from alaya.index.models import get_active_model
    active_model = get_active_model().name

    table = store._get_table()

    try:
        table.delete(f"path = '{_sq(path)}'")
    except _STORE_ERRORS as e:
        logger.warning("Failed to delete existing chunks for %s before upsert: %s", path, e)

    if not chunks:
        return

    # Check if the table has the embedding_model column (absent on old schemas)
    has_model_col = "embedding_model" in {f.name for f in table.schema}

    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        row = {
            "path": chunk.path,
            "title": chunk.title,
            "directory": chunk.directory,
            "tags": ",".join(chunk.tags),
            "modified_date": chunk.modified_date,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "vector": embedding.tolist(),
        }
        if has_model_col:
            row["embedding_model"] = active_model
        rows.append(row)

    table.add(rows)


def delete_note_from_index(path: str, store: VaultStore) -> None:
    """Remove all chunks for `path` from the index."""
    try:
        table = store._get_table()
        table.delete(f"path = '{_sq(path)}'")
    except _STORE_ERRORS as e:
        logger.warning("Failed to delete %s from index: %s", path, e)


def update_metadata(
    old_path: str,
    new_path: str,
    new_title: str | None,
    new_tags: list[str] | None,
    store: VaultStore,
) -> None:
    """Update path/title/tags on all chunks for old_path without re-embedding."""
    new_directory = new_path.split("/")[0] if "/" in new_path else ""

    try:
        table = store._get_table()
        existing = table.search().where(f"path = '{_sq(old_path)}'").limit(10000).to_list()
        if not existing:
            return

        table.delete(f"path = '{_sq(old_path)}'")

        updated = []
        for row in existing:
            row = dict(row)
            row["path"] = new_path
            row["directory"] = new_directory
            if new_title is not None:
                row["title"] = new_title
            if new_tags is not None:
                row["tags"] = ",".join(new_tags)
            # remove LanceDB internal fields before re-inserting
            row.pop("_distance", None)
            updated.append(row)

        table.add(updated)
    except _STORE_ERRORS as e:
        logger.warning("Failed to update metadata for %s: %s", old_path, e)


def hybrid_search(
    query: str,
    query_embedding: np.ndarray,
    store: VaultStore,
    directory: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """Vector ANN search with optional metadata pre-filter.

    Returns list of {path, title, directory, score, text}.
    """
    if store.count() == 0:
        return []

    try:
        table = store._get_table()

        q = table.search(query_embedding.tolist(), vector_column_name="vector")

        filters = []
        if directory:
            filters.append(f"directory = '{_sq(directory)}'")
        if tags:
            for tag in tags:
                # tags column is comma-separated; match as substring
                filters.append(f"tags LIKE '%{_sq_like(tag)}%'")
        if filters:
            q = q.where(" AND ".join(filters))

        # fetch more candidates than limit to allow deduplication by path
        results = q.limit(limit * 4).to_list()

        # score each chunk, then keep best chunk per path (dedup)
        seen: dict[str, dict] = {}
        for row in results:
            text = row.get("text", "").lower()
            keyword_boost = sum(1 for term in query.lower().split() if term in text)
            score = float(row.get("_distance", 1.0))
            similarity = max(0.0, 1.0 - score)
            final_score = min(1.0, similarity + keyword_boost * 0.05)

            path = row["path"]
            if path not in seen or final_score > seen[path]["score"]:
                seen[path] = {
                    "path": path,
                    "title": row["title"],
                    "directory": row["directory"],
                    "score": round(final_score, 3),
                    "text": row["text"],
                }

        output = sorted(seen.values(), key=lambda r: r["score"], reverse=True)
        return output[:limit]

    except _STORE_ERRORS as e:
        logger.warning("hybrid_search failed for query %r: %s", query, e)
        return []


_store_cache: dict[Path, VaultStore] = {}
_store_lock = threading.Lock()


def get_store(vault: Path) -> VaultStore:
    """Return the VaultStore for a given vault root, creating it once per process.

    Uses double-checked locking so the common path (cache hit) avoids lock
    overhead while concurrent first-time calls still produce exactly one instance.
    """
    resolved = vault.resolve()
    if resolved in _store_cache:
        return _store_cache[resolved]
    with _store_lock:
        if resolved not in _store_cache:
            _store_cache[resolved] = VaultStore(db_path=resolved / ".zk" / "vectors")
        return _store_cache[resolved]


def reset_store() -> None:
    """Clear the store cache. Intended for use in tests only."""
    with _store_lock:
        _store_cache.clear()
