"""Every vault-mutating tool emits a NoteEvent with a vault-relative .md path (#149)."""
from pathlib import Path

import pytest

from alaya.events import EventType, clear_listeners, on_note_change
from alaya.tools.edit import extract_section, replace_section
from alaya.tools.inbox import capture_to_inbox, clear_inbox_item
from alaya.tools.structure import rename_note
from alaya.tools.tasks import complete_todo, get_todos


@pytest.fixture
def events():
    clear_listeners()
    received = []
    on_note_change(received.append)
    yield received
    clear_listeners()


def _modified(events) -> list[str]:
    return [e.path for e in events if e.event_type == EventType.MODIFIED]


def test_replace_section_emits(vault: Path, events) -> None:
    replace_section("projects/second-brain.md", "notes", "new", vault)
    assert _modified(events) == ["projects/second-brain.md"]


def test_replace_section_missing_does_not_emit(vault: Path, events) -> None:
    with pytest.raises(ValueError):
        replace_section("projects/second-brain.md", "Nope", "new", vault)
    assert events == []


def test_extract_section_emits_source_and_new(vault: Path, events) -> None:
    new_path = extract_section("projects/second-brain.md", "Notes", "Extracted", "ideas", vault)
    assert (EventType.CREATED, new_path) in [(e.event_type, e.path) for e in events]
    assert _modified(events) == ["projects/second-brain.md"]


def test_complete_todo_emits(vault: Path, events) -> None:
    todo = next(t for t in get_todos(vault, directories=["projects"]) if "scaffold" in t["text"])
    complete_todo(todo["path"], todo["line"], todo["text"], vault)
    assert _modified(events) == [todo["path"]]


def test_complete_todo_fuzzy_emits_once(vault: Path, events) -> None:
    todo = next(t for t in get_todos(vault, directories=["projects"]) if "scaffold" in t["text"])
    complete_todo(todo["path"], todo["line"] + 3, todo["text"], vault)
    assert "- [x] scaffold" in (vault / todo["path"]).read_text()
    assert _modified(events) == [todo["path"]]


def test_complete_todo_missing_does_not_emit(vault: Path, events) -> None:
    with pytest.raises(ValueError):
        complete_todo("projects/second-brain.md", 1, "no such task", vault)
    assert events == []


def test_inbox_capture_and_clear_emit(vault: Path, events) -> None:
    capture_to_inbox("buy milk", vault)
    clear_inbox_item("buy milk", vault)
    assert _modified(events) == ["inbox.md", "inbox.md"]
    with pytest.raises(ValueError):
        clear_inbox_item("buy milk", vault)
    assert len(events) == 2


def test_rename_emits_moved_then_linking_notes(vault: Path, events) -> None:
    (vault / "ideas/linker.md").write_text("---\ntitle: linker\n---\nsee [[voice-capture]]\n")
    rename_note("ideas/voice-capture.md", "audio-capture", vault)
    kinds = [(e.event_type, e.path) for e in events]
    assert kinds[0] == (EventType.MOVED, "ideas/audio-capture.md")
    assert (EventType.MODIFIED, "ideas/linker.md") in kinds[1:]


def test_emitted_path_makes_the_watcher_skip(vault: Path, events) -> None:
    """The server listener marks event.path indexed; the watcher must look up the same key."""
    from unittest.mock import MagicMock

    from alaya.watcher import VaultEventHandler

    handler = VaultEventHandler(vault=vault, store=MagicMock())
    on_note_change(lambda e: handler.mark_indexed(e.path))
    replace_section("projects/second-brain.md", "Notes", "new", vault)
    todo = next(t for t in get_todos(vault, directories=["projects"]) if "scaffold" in t["text"])
    complete_todo(todo["path"], todo["line"], todo["text"], vault)
    capture_to_inbox("x", vault)

    for path in ("projects/second-brain.md", todo["path"], "inbox.md"):
        assert handler._was_recently_indexed(handler._relative(str(vault / path)))
