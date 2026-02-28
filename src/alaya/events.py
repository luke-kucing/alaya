"""Lightweight event system for write-through index updates."""
from __future__ import annotations

from typing import Callable

_listeners: list[Callable[[str, str], None]] = []


def on_note_change(callback: Callable[[str, str], None]) -> None:
    """Register a callback for (event_type, relative_path) events."""
    _listeners.append(callback)


def emit(event_type: str, path: str) -> None:
    """Fire all registered listeners with the given event_type and path."""
    for listener in _listeners:
        listener(event_type, path)


def clear_listeners() -> None:
    """Remove all registered listeners. Intended for use in tests only."""
    _listeners.clear()
