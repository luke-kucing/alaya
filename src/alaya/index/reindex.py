"""Vault reindex: full rebuild and incremental (skip unchanged files)."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from alaya.index.embedder import chunk_note, embed_chunks
from alaya.index.store import upsert_note, delete_note_from_index, get_store
from alaya.vault import iter_vault_md as _iter_vault_md


@dataclass
class ReindexResult:
    notes_indexed: int
    chunks_created: int
    duration_seconds: float
    notes_skipped: int = 0
    notes_deleted: int = 0


def _bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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

    Uses a JSON state file (.zk/index_state.json) to track mtime, content hash,
    and active embedding model per file. If the active model has changed since the
    last run, all files are treated as dirty and re-embedded. Cleans up deleted
    files from the index.
    """
    from alaya.index.models import get_active_model
    active_model = get_active_model().name

    if store is None:
        store = get_store(vault_root)

    state_file = vault_root / ".zk" / "index_state.json"
    raw_state: dict = json.loads(state_file.read_text()) if state_file.exists() else {}

    # State file format: {"_model": "...", "files": {rel_path: {mtime, hash}}}
    # Legacy format (flat dict of paths) is also accepted.
    stored_model = raw_state.get("_model")
    prev_files: dict = raw_state.get("files", raw_state if "_model" not in raw_state else {})
    model_changed = stored_model is not None and stored_model != active_model
    prev_state = {} if model_changed else prev_files

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

        # Read file once for both hash check and embedding
        raw_bytes = md_file.read_bytes()
        file_hash = _bytes_hash(raw_bytes)

        # Slow path: mtime changed — check hash before paying embedding cost
        if prev and prev.get("hash") == file_hash:
            new_state[rel] = {"mtime": mtime, "hash": file_hash}
            notes_skipped += 1
            continue

        # Content changed — re-embed
        content = raw_bytes.decode()
        chunks = chunk_note(rel, content)
        if chunks:
            embeddings = embed_chunks(chunks)
            upsert_note(rel, chunks, embeddings, store)
            chunks_created += len(chunks)
            notes_indexed += 1

        new_state[rel] = {"mtime": mtime, "hash": file_hash}

    # Remove index entries for files no longer in the vault
    # Compare against prev_files (not prev_state, which is empty on model change)
    deleted = set(prev_files) - set(new_state)
    for old_path in deleted:
        delete_note_from_index(old_path, store)

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"_model": active_model, "files": new_state}, indent=2))

    duration = time.monotonic() - start
    return ReindexResult(
        notes_indexed=notes_indexed,
        chunks_created=chunks_created,
        duration_seconds=round(duration, 2),
        notes_skipped=notes_skipped,
        notes_deleted=len(deleted),
    )


_REEMBED_BATCH = 20      # notes per batch
_REEMBED_SLEEP = 0.5     # seconds between batches


def reembed_background(vault_root: Path, from_model: str, to_model: str, store=None) -> None:
    """Re-embed all notes in batches as a background migration.

    Called in a daemon thread when the active embedding model changes.
    Updates health.py migration progress so vault_health can report it.
    On completion writes an updated state file so incremental reindex
    knows everything is current.
    """
    import logging
    from alaya.index import health

    logger = logging.getLogger(__name__)

    if store is None:
        store = get_store(vault_root)

    md_files = list(_iter_vault_md(vault_root))
    total = len(md_files)
    health.start_migration(from_model, to_model, total)
    logger.info("Background re-embed started: %s -> %s (%d notes)", from_model, to_model, total)

    done = 0
    new_state: dict = {}

    for i in range(0, total, _REEMBED_BATCH):
        batch = md_files[i:i + _REEMBED_BATCH]
        for md_file in batch:
            rel = str(md_file.relative_to(vault_root))
            try:
                mtime = md_file.stat().st_mtime
                content = md_file.read_text()
                chunks = chunk_note(rel, content)
                if chunks:
                    embeddings = embed_chunks(chunks)
                    upsert_note(rel, chunks, embeddings, store)
                new_state[rel] = {"mtime": mtime, "hash": _bytes_hash(md_file.read_bytes())}
                done += 1
            except Exception as e:
                logger.warning("Re-embed failed for %s: %s", rel, e)

        health.update_migration_progress(done)
        if i + _REEMBED_BATCH < total:
            time.sleep(_REEMBED_SLEEP)

    # Write updated state file
    state_file = vault_root / ".zk" / "index_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"_model": to_model, "files": new_state}, indent=2))

    health.finish_migration()
    logger.info("Background re-embed complete: %d/%d notes", done, total)
