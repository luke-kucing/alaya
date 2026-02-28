"""LanceDB store: upsert_note, delete_note_from_index, hybrid_search."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

_TABLE_NAME = "notes"
_DIM = 768


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
            if _TABLE_NAME in db.list_tables():
                self._table = db.open_table(_TABLE_NAME)
            else:
                schema = pa.schema([
                    pa.field("path", pa.string()),
                    pa.field("title", pa.string()),
                    pa.field("directory", pa.string()),
                    pa.field("tags", pa.string()),  # comma-separated
                    pa.field("modified_date", pa.string()),
                    pa.field("chunk_index", pa.int32()),
                    pa.field("text", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), _DIM)),
                ])
                self._table = db.create_table(_TABLE_NAME, schema=schema)
        return self._table

    def count(self) -> int:
        try:
            return self._get_table().count_rows()
        except Exception:
            return 0


def upsert_note(
    path: str,
    chunks: list,
    embeddings: list[np.ndarray],
    store: VaultStore,
) -> None:
    """Replace all chunks for `path` with the new chunks + embeddings."""
    table = store._get_table()

    # delete existing rows for this path
    try:
        table.delete(f"path = '{path}'")
    except Exception:
        pass

    if not chunks:
        return

    rows = []
    for chunk, embedding in zip(chunks, embeddings):
        rows.append({
            "path": chunk.path,
            "title": chunk.title,
            "directory": chunk.directory,
            "tags": ",".join(chunk.tags),
            "modified_date": chunk.modified_date,
            "chunk_index": chunk.chunk_index,
            "text": chunk.text,
            "vector": embedding.tolist(),
        })

    table.add(rows)


def delete_note_from_index(path: str, store: VaultStore) -> None:
    """Remove all chunks for `path` from the index."""
    try:
        table = store._get_table()
        table.delete(f"path = '{path}'")
    except Exception:
        pass


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

        if directory:
            q = q.where(f"directory = '{directory}'")

        results = q.limit(limit).to_list()

        output = []
        for row in results:
            # keyword re-rank: boost if query terms appear in text
            text = row.get("text", "").lower()
            keyword_boost = sum(1 for term in query.lower().split() if term in text)
            score = float(row.get("_distance", 1.0))
            # convert distance to similarity (lower distance = higher score)
            similarity = max(0.0, 1.0 - score)
            final_score = min(1.0, similarity + keyword_boost * 0.05)

            output.append({
                "path": row["path"],
                "title": row["title"],
                "directory": row["directory"],
                "score": round(final_score, 3),
                "text": row["text"],
            })

        return output

    except Exception:
        return []


def get_store(vault: Path) -> VaultStore:
    """Return the VaultStore for a given vault root."""
    return VaultStore(db_path=vault / ".zk" / "vectors")
