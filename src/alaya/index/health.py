"""Index health tracking: record failed index operations for user-visible diagnostics."""
from __future__ import annotations

import threading
import time
from pathlib import Path

# path -> (error_message, timestamp)
_failed_paths: dict[str, tuple[str, float]] = {}
_last_success_ts: float | None = None

# Migration progress: set when a background model re-embed is running
_migration: dict | None = None  # {from_model, to_model, total, done}

_lock = threading.Lock()


def record_failure(path: str, error: str) -> None:
    with _lock:
        _failed_paths[path] = (error, time.monotonic())


def record_success(path: str) -> None:
    global _last_success_ts
    with _lock:
        _failed_paths.pop(path, None)
        _last_success_ts = time.monotonic()


def start_migration(from_model: str, to_model: str, total: int) -> None:
    """Record that a background model migration has started."""
    global _migration
    with _lock:
        _migration = {"from_model": from_model, "to_model": to_model, "total": total, "done": 0}


def update_migration_progress(done: int) -> None:
    """Update the count of notes re-embedded so far."""
    with _lock:
        if _migration is not None:
            _migration["done"] = done


def finish_migration() -> None:
    """Mark migration as complete."""
    global _migration
    with _lock:
        _migration = None


def get_status() -> dict:
    """Return a consistent snapshot of current index health."""
    with _lock:
        failed = {path: msg for path, (msg, _) in _failed_paths.items()}
        last_ok = _last_success_ts
        migration = dict(_migration) if _migration else None
    return {
        "failed_paths": failed,
        "last_success_ago_seconds": round(time.monotonic() - last_ok, 1) if last_ok else None,
        "migration": migration,
    }


# Background threads server.py starts that rewrite the index.
_REINDEX_THREADS = ("alaya-schema-reindex", "alaya-reembed")


def index_lag(vault: Path, last_write: float) -> tuple[int, float | None]:
    """Notes edited after the index's last write, and seconds since the oldest such edit.

    A lower bound: an edit made before some later, unrelated index write is not counted.
    """
    from alaya.vault import iter_vault_md
    stale = []
    for md in iter_vault_md(vault):
        try:
            mtime = md.stat().st_mtime
        except OSError:
            continue
        if mtime > last_write:
            stale.append(mtime)
    return len(stale), (round(time.time() - min(stale), 1) if stale else None)


def report(vault: Path, store) -> str:
    """Markdown health report for the vault_health tool (read by agents and people)."""
    from alaya.index.models import get_active_model
    from alaya.index.store import get_index_model

    status = get_status()
    lines = [f"Indexed chunks: {store.count()}"]

    last_ago = status["last_success_ago_seconds"]
    if last_ago is None:
        lines.append("Last successful index: never (no events processed yet)")
    else:
        lines.append(f"Last successful index: {last_ago}s ago")

    last_write = store.last_write_time()
    if last_write is None:
        lines.append("Index lag: unknown (no index yet)")
    else:
        stale, lag = index_lag(vault, last_write)
        lines.append(f"Index lag: {lag}s ({stale} notes edited since the last index write)" if stale
                     else "Index lag: 0s (no notes edited since the last index write)")

    running = [t.name for t in threading.enumerate() if t.name in _REINDEX_THREADS and t.is_alive()]
    lines.append(f"Reindex in progress: {'yes (' + ', '.join(running) + ')' if running else 'no'}")
    if status["migration"]:
        m = status["migration"]
        lines.append(f"Re-embed: {m['done']}/{m['total']} notes ({m['from_model']} -> {m['to_model']})")

    cfg = get_active_model()
    indexed_with = get_index_model(store)
    lines.append(f"Embedder: fastembed {cfg.key} ({cfg.name}, {cfg.dimensions} dims)")
    if indexed_with and indexed_with != cfg.key:
        lines.append(f"Index built with: {indexed_with} (differs from the active embedder)")
    lines.append("Store: LanceDB")

    failed = status["failed_paths"]
    if failed:
        lines.append(f"\nFailed paths ({len(failed)}):")
        for path, msg in failed.items():
            lines.append(f"  {path}: {msg}")
    else:
        lines.append("No failed paths.")
    return "\n".join(lines)


def reset() -> None:
    """Clear all state. Intended for use in tests only."""
    global _last_success_ts, _migration
    with _lock:
        _failed_paths.clear()
        _last_success_ts = None
        _migration = None
