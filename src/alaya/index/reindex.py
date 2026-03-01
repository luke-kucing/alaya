"""Vault reindex: full rebuild and incremental (skip unchanged files)."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from alaya.index.embedder import chunk_note, embed_chunks
from alaya.index.store import upsert_note, delete_note_from_index, get_store
from alaya.tools.structure import _iter_vault_md


@dataclass
class ReindexResult:
    notes_indexed: int
    chunks_created: int
    duration_seconds: float
    notes_skipped: int = 0
    notes_deleted: int = 0


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reindex_all(vault_root: Path, store=None) -> ReindexResult:
    """Rebuild the full LanceDB index for the vault.

    Enumerates all .md files, chunks each one, embeds in batches, writes to store.
    """
    if store is None:
        store = get_store(vault_root)

    start = time.monotonic()
    notes_indexed = 0
    chunks_created = 0

    for md_file in _iter_vault_md(vault_root):
        rel = str(md_file.relative_to(vault_root))
        content = md_file.read_text()
        chunks = chunk_note(rel, content)
        if not chunks:
            continue
        embeddings = embed_chunks(chunks)
        upsert_note(rel, chunks, embeddings, store)
        notes_indexed += 1
        chunks_created += len(chunks)

    duration = time.monotonic() - start
    return ReindexResult(
        notes_indexed=notes_indexed,
        chunks_created=chunks_created,
        duration_seconds=round(duration, 2),
    )


def reindex_incremental(vault_root: Path, store=None) -> ReindexResult:
    """Reindex only files that have changed since the last run.

    Uses a JSON state file (.zk/index_state.json) to track mtime and content hash
    per file. Skips files where mtime is unchanged (fast path), or where mtime
    changed but hash is the same (touch without content change). Cleans up
    deleted files from the index.
    """
    if store is None:
        store = get_store(vault_root)

    state_file = vault_root / ".zk" / "index_state.json"
    prev_state: dict = json.loads(state_file.read_text()) if state_file.exists() else {}

    new_state: dict = {}
    notes_indexed = 0
    chunks_created = 0
    notes_skipped = 0
    start = time.monotonic()

    for md_file in _iter_vault_md(vault_root):
        rel = str(md_file.relative_to(vault_root))
        try:
            mtime = md_file.stat().st_mtime
        except OSError:
            continue

        prev = prev_state.get(rel)

        # Fast path: mtime unchanged — definitely not modified
        if prev and prev.get("mtime") == mtime:
            new_state[rel] = prev
            notes_skipped += 1
            continue

        # Slow path: mtime changed — check hash before paying embedding cost
        file_hash = _file_hash(md_file)
        if prev and prev.get("hash") == file_hash:
            new_state[rel] = {"mtime": mtime, "hash": file_hash}
            notes_skipped += 1
            continue

        # Content changed — re-embed
        content = md_file.read_text()
        chunks = chunk_note(rel, content)
        if chunks:
            embeddings = embed_chunks(chunks)
            upsert_note(rel, chunks, embeddings, store)
            chunks_created += len(chunks)
            notes_indexed += 1

        new_state[rel] = {"mtime": mtime, "hash": file_hash}

    # Remove index entries for files no longer in the vault
    deleted = set(prev_state) - set(new_state)
    for old_path in deleted:
        delete_note_from_index(old_path, store)

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(new_state, indent=2))

    duration = time.monotonic() - start
    return ReindexResult(
        notes_indexed=notes_indexed,
        chunks_created=chunks_created,
        duration_seconds=round(duration, 2),
        notes_skipped=notes_skipped,
        notes_deleted=len(deleted),
    )
