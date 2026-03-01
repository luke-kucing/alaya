"""Index health tracking: record failed index operations for user-visible diagnostics."""
from __future__ import annotations

import threading
import time

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


def reset() -> None:
    """Clear all state. Intended for use in tests only."""
    global _last_success_ts, _migration
    with _lock:
        _failed_paths.clear()
        _last_success_ts = None
        _migration = None
