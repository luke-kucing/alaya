"""Index health tracking: record failed index operations for user-visible diagnostics."""
from __future__ import annotations

import time

# path -> (error_message, timestamp)
_failed_paths: dict[str, tuple[str, float]] = {}
_last_success_ts: float | None = None


def record_failure(path: str, error: str) -> None:
    _failed_paths[path] = (error, time.monotonic())


def record_success(path: str) -> None:
    global _last_success_ts
    _failed_paths.pop(path, None)
    _last_success_ts = time.monotonic()


def get_status() -> dict:
    """Return a snapshot of current index health."""
    failed = {
        path: msg
        for path, (msg, _) in _failed_paths.items()
    }
    last_ok = _last_success_ts
    return {
        "failed_paths": failed,
        "last_success_ago_seconds": round(time.monotonic() - last_ok, 1) if last_ok else None,
    }


def reset() -> None:
    """Clear all state. Intended for use in tests only."""
    global _last_success_ts
    _failed_paths.clear()
    _last_success_ts = None
