"""Full vault reindex: enumerate all .md files, chunk, embed, write to LanceDB atomically."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ReindexResult:
    notes_indexed: int
    chunks_created: int
    duration_seconds: float


def reindex_all(vault_root: Path, store=None) -> ReindexResult:
    """Rebuild the full LanceDB index for the vault.

    Enumerates all .md files, chunks each one, embeds in batches, writes to store.
    """
    from alaya.index.embedder import chunk_note, embed_chunks
    from alaya.index.store import upsert_note, VaultStore, get_store

    if store is None:
        store = get_store(vault_root)

    start = time.monotonic()
    notes_indexed = 0
    chunks_created = 0

    md_files = [
        f for f in vault_root.rglob("*.md")
        if ".zk" not in f.parts
    ]

    for md_file in md_files:
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
