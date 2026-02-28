"""Lightweight event system for write-through index updates."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class NoteEvent:
    event_type: str  # "created", "modified", "deleted", "moved"
    path: str        # relative path of the affected note
    old_path: str | None = None  # set only for "moved" events


_listeners: list[Callable[[NoteEvent], None]] = []


def on_note_change(callback: Callable[[NoteEvent], None]) -> None:
    """Register a callback for note change events."""
    _listeners.append(callback)


def emit(event: NoteEvent) -> None:
    """Fire all registered listeners with the given event."""
    for listener in _listeners:
        listener(event)


def clear_listeners() -> None:
    """Remove all registered listeners. Intended for use in tests only."""
    _listeners.clear()
