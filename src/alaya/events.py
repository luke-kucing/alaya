"""Lightweight event system for write-through index updates."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class NoteEvent:
    event_type: str  # "created", "modified", "deleted", "moved"
    path: str        # relative path of the affected note
    old_path: str | None = None  # set only for "moved" events


_listeners: list[Callable[[NoteEvent], None]] = []
_listeners_lock = threading.Lock()


def on_note_change(callback: Callable[[NoteEvent], None]) -> None:
    """Register a callback for note change events."""
    with _listeners_lock:
        _listeners.append(callback)


def emit(event: NoteEvent) -> None:
    """Fire all registered listeners with the given event.

    Takes a snapshot of the listener list under the lock so that concurrent
    registration cannot cause RuntimeError or silent skips during iteration.
    """
    with _listeners_lock:
        snapshot = list(_listeners)
    for listener in snapshot:
        listener(event)


def clear_listeners() -> None:
    """Remove all registered listeners. Intended for use in tests only."""
    with _listeners_lock:
        _listeners.clear()
