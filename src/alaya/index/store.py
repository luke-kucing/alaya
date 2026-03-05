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
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%")
    escaped = escaped.replace("_", "\\_")
    return escaped


@dataclass
class VaultStore:
    """Thin wrapper around a LanceDB table for the vault index."""
    db_path: Path
    _db: Any = None
    _table: Any = None
    _init_lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._init_lock = threading.Lock()
        self._needs_reindex: bool = False
        self._fts_ready: bool = False

    def _connect(self) -> Any:
        if self._db is None:
            import lancedb
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    def _get_table(self) -> Any:
        if self._table is None:
            with self._init_lock:
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
                    except (pa.ArrowInvalid, OSError, ValueError):
                        # Schema mismatch (e.g. old schema, dimension change, LanceDB version upgrade).
                        # Drop and recreate so the table is always consistent with the current schema.
                        # A background reindex will repopulate it; search degrades to zk fallback meanwhile.
                        logger.warning(
                            "Schema mismatch on table %r — dropping and recreating. "
                            "Background reindex will repopulate the index.",
                            _TABLE_NAME,
                        )
                        db.drop_table(_TABLE_NAME)
                        self._table = db.create_table(_TABLE_NAME, schema=schema)
                        self._needs_reindex = True
        return self._table

    def take_needs_reindex(self) -> bool:
        """Return and clear the needs_reindex flag. Thread-safe via _init_lock."""
        with self._init_lock:
            val = self._needs_reindex
            self._needs_reindex = False
        return val

    def count(self) -> int:
        try:
            return self._get_table().count_rows()
        except _STORE_ERRORS:
            return 0

    def ensure_fts_index(self) -> bool:
        """Create FTS index on the text column if not already done.

        Returns True if FTS is available for hybrid search.
        Safe to call repeatedly — only creates the index once.
        """
        if self._fts_ready:
            return True
        try:
            table = self._get_table()
            if table.count_rows() == 0:
                return False
            table.create_fts_index("text", replace=True)
            self._fts_ready = True
            return True
        except _STORE_ERRORS as e:
            logger.debug("FTS index creation failed (will use vector-only): %s", e)
            return False


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
    active_model = get_active_model().key

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
            "tags": "," + ",".join(chunk.tags) + "," if chunk.tags else "",
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
    if old_path == new_path and new_title is None and new_tags is None:
        return

    new_directory = new_path.split("/")[0] if "/" in new_path else ""

    try:
        table = store._get_table()
        existing = table.search().where(f"path = '{_sq(old_path)}'").limit(10000).to_list()
        if not existing:
            return

        updated = []
        for row in existing:
            row = dict(row)
            row["path"] = new_path
            row["directory"] = new_directory
            if new_title is not None:
                row["title"] = new_title
            if new_tags is not None:
                row["tags"] = "," + ",".join(new_tags) + "," if new_tags else ""
            # remove LanceDB internal fields before re-inserting
            row.pop("_distance", None)
            updated.append(row)

        # When paths differ, add first to avoid data loss on failure.
        # When paths are equal, we must delete first since old and new
        # rows share the same path and can't be distinguished.
        if old_path != new_path:
            table.add(updated)
            table.delete(f"path = '{_sq(old_path)}'")
        else:
            table.delete(f"path = '{_sq(old_path)}'")
            table.add(updated)
    except _STORE_ERRORS as e:
        logger.warning("Failed to update metadata for %s: %s", old_path, e)


def _build_filter(
    directory: str | None,
    tags: list[str] | None,
    since: str | None,
) -> str | None:
    """Build a SQL WHERE clause from optional metadata filters."""
    filters = []
    if directory:
        filters.append(f"directory = '{_sq(directory)}'")
    if tags:
        for tag in tags:
            filters.append(f"tags LIKE '%,{_sq_like(tag)},%' ESCAPE '\\'")
    if since:
        filters.append(f"modified_date >= '{_sq(since)}'")
    return " AND ".join(filters) if filters else None


def _dedup_by_path(results: list[dict], limit: int) -> list[dict]:
    """Keep the highest-scoring chunk per note path."""
    seen: dict[str, dict] = {}
    for row in results:
        score = float(row.get("_relevance_score", 0.0))
        path = row["path"]
        if path not in seen or score > seen[path]["score"]:
            seen[path] = {
                "path": path,
                "title": row["title"],
                "directory": row["directory"],
                "score": round(score, 3),
                "text": row["text"],
            }
    output = sorted(seen.values(), key=lambda r: r["score"], reverse=True)
    return output[:limit]


def _dedup_by_path_vector(results: list[dict], limit: int) -> list[dict]:
    """Keep the highest-scoring chunk per note path (vector-only results use _distance)."""
    seen: dict[str, dict] = {}
    for row in results:
        distance = float(row.get("_distance", 1.0))
        score = max(0.0, 1.0 - distance)
        path = row["path"]
        if path not in seen or score > seen[path]["score"]:
            seen[path] = {
                "path": path,
                "title": row["title"],
                "directory": row["directory"],
                "score": round(score, 3),
                "text": row["text"],
            }
    output = sorted(seen.values(), key=lambda r: r["score"], reverse=True)
    return output[:limit]


def hybrid_search(
    query: str,
    query_embedding: np.ndarray,
    store: VaultStore,
    directory: str | None = None,
    tags: list[str] | None = None,
    since: str | None = None,
    limit: int = 10,
    rerank: bool = False,
) -> list[dict]:
    """Search using LanceDB native hybrid search (vector + BM25 FTS) with RRF.

    Falls back to vector-only search if the FTS index is not available.
    When rerank=True, applies a cross-encoder reranker on the top candidates
    for higher precision (adds latency).
    Returns list of {path, title, directory, score, text}.
    """
    if store.count() == 0:
        return []

    where = _build_filter(directory, tags, since)
    # When reranking, fetch more candidates so the cross-encoder has a larger pool
    candidate_limit = limit * 8 if rerank else limit * 4

    # Try native hybrid search (vector + FTS with RRF reranking)
    results: list[dict] = []
    if store.ensure_fts_index():
        try:
            raw = _hybrid_search_native(query, query_embedding, store, where, candidate_limit)
            results = _dedup_by_path(raw, candidate_limit)
        except _STORE_ERRORS as e:
            logger.debug("Native hybrid search failed, falling back to vector-only: %s", e)

    # Fallback: vector-only search
    if not results:
        try:
            results = _vector_search(query_embedding, store, where, candidate_limit, candidate_limit)
        except _STORE_ERRORS as e:
            logger.warning("hybrid_search failed for query %r: %s", query, e)
            return []

    # Optional cross-encoder reranking for higher precision
    if rerank and results:
        results = _cross_encoder_rerank(query, results, limit)
    else:
        results = results[:limit]

    return results


def _hybrid_search_native(
    query: str,
    query_embedding: np.ndarray,
    store: VaultStore,
    where: str | None,
    fetch_limit: int,
) -> list[dict]:
    """Run LanceDB native hybrid search: vector + FTS combined via RRF."""
    from lancedb.rerankers import RRFReranker

    table = store._get_table()
    q = (
        table.search(query, query_type="hybrid", vector_column_name="vector")
        .vector(query_embedding.tolist())
        .text(query)
        .rerank(RRFReranker())
        .limit(fetch_limit)
    )
    if where:
        q = q.where(where)
    return q.to_list()


def _vector_search(
    query_embedding: np.ndarray,
    store: VaultStore,
    where: str | None,
    fetch_limit: int,
    limit: int,
) -> list[dict]:
    """Fallback: vector-only ANN search."""
    table = store._get_table()
    q = table.search(query_embedding.tolist(), vector_column_name="vector").limit(fetch_limit)
    if where:
        q = q.where(where)
    results = q.to_list()
    return _dedup_by_path_vector(results, limit)


_reranker_lock = threading.Lock()
_reranker_instance: Any = None


def _get_cross_encoder() -> Any:
    """Lazy-load the cross-encoder model (singleton)."""
    global _reranker_instance
    if _reranker_instance is None:
        with _reranker_lock:
            if _reranker_instance is None:
                from sentence_transformers import CrossEncoder
                _reranker_instance = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker_instance


def _cross_encoder_rerank(query: str, results: list[dict], limit: int) -> list[dict]:
    """Rerank results using a cross-encoder for higher precision."""
    try:
        model = _get_cross_encoder()
        pairs = [[query, r["text"]] for r in results]
        scores = model.predict(pairs)
        for r, score in zip(results, scores):
            r["score"] = round(float(score), 3)
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:limit]
    except Exception as e:
        logger.warning("Cross-encoder reranking failed, returning RRF results: %s", e)
        return results[:limit]


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
