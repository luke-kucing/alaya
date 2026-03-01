"""Tests for the event system used by write-through index updates."""
import pytest

from alaya.events import NoteEvent, EventType, on_note_change, emit, clear_listeners


class TestEventSystem:
    def setup_method(self):
        clear_listeners()

    def test_emit_calls_registered_listener(self):
        received = []
        on_note_change(lambda event: received.append(event))
        emit(NoteEvent(EventType.CREATED, "notes/test.md"))
        assert len(received) == 1
        assert received[0].event_type == EventType.CREATED
        assert received[0].path == "notes/test.md"

    def test_multiple_listeners_all_called(self):
        calls_a, calls_b = [], []
        on_note_change(lambda e: calls_a.append(e.event_type))
        on_note_change(lambda e: calls_b.append(e.event_type))
        emit(NoteEvent(EventType.MODIFIED, "notes/foo.md"))
        assert calls_a == [EventType.MODIFIED]
        assert calls_b == [EventType.MODIFIED]

    def test_clear_listeners(self):
        received = []
        on_note_change(lambda e: received.append(e))
        clear_listeners()
        emit(NoteEvent(EventType.CREATED, "notes/test.md"))
        assert received == []

    def test_no_listeners_does_not_raise(self):
        emit(NoteEvent(EventType.DELETED, "notes/gone.md"))  # should not raise

    def test_moved_event_has_old_path(self):
        received = []
        on_note_change(lambda e: received.append(e))
        emit(NoteEvent(EventType.MOVED, "notes/new.md", old_path="notes/old.md"))
        assert received[0].old_path == "notes/old.md"
        assert received[0].path == "notes/new.md"


class TestUpdateMetadata:
    """Tests for store.update_metadata (path/title/tags without re-embedding)."""

    def test_update_metadata_changes_path(self, tmp_path):
        from alaya.index.store import VaultStore, upsert_note, update_metadata
        from alaya.index.embedder import Chunk
        import numpy as np

        store = VaultStore(db_path=tmp_path / "vectors")
        chunk = Chunk(
            path="old/note.md", title="Old", tags=["a"],
            directory="old", modified_date="2026-01-01", chunk_index=0,
            text="Some text.",
        )
        embedding = np.zeros(768, dtype=np.float32)
        upsert_note("old/note.md", [chunk], [embedding], store)

        update_metadata("old/note.md", "new/note.md", new_title="New", new_tags=["b"], store=store)

        rows = store._get_table().search().limit(100).to_list()
        assert len(rows) == 1
        assert rows[0]["path"] == "new/note.md"
        assert rows[0]["title"] == "New"
        assert rows[0]["tags"] == "b"

    def test_update_metadata_no_title_change(self, tmp_path):
        from alaya.index.store import VaultStore, upsert_note, update_metadata
        from alaya.index.embedder import Chunk
        import numpy as np

        store = VaultStore(db_path=tmp_path / "vectors")
        chunk = Chunk(
            path="notes/a.md", title="Original", tags=[],
            directory="notes", modified_date="2026-01-01", chunk_index=0,
            text="Text.",
        )
        embedding = np.zeros(768, dtype=np.float32)
        upsert_note("notes/a.md", [chunk], [embedding], store)

        update_metadata("notes/a.md", "notes/b.md", new_title=None, new_tags=None, store=store)

        rows = store._get_table().search().limit(100).to_list()
        assert rows[0]["path"] == "notes/b.md"
        assert rows[0]["title"] == "Original"  # unchanged


class TestEventThreadSafety:
    def setup_method(self):
        clear_listeners()

    def test_registering_listener_from_within_callback_does_not_crash(self):
        """A listener that registers another listener during emit must not raise."""
        registered_during_emit = []

        def callback(event):
            # register a new listener while emit() is iterating
            on_note_change(lambda e: registered_during_emit.append(e))

        on_note_change(callback)
        emit(NoteEvent(EventType.CREATED, "notes/test.md"))  # must not raise

    def test_concurrent_emit_and_register_no_crash(self):
        """Concurrent emit() and on_note_change() from different threads must not crash."""
        import threading
        errors = []

        def register():
            try:
                for _ in range(50):
                    on_note_change(lambda e: None)
            except Exception as e:
                errors.append(e)

        def fire():
            try:
                for _ in range(50):
                    emit(NoteEvent(EventType.MODIFIED, "notes/foo.md"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register), threading.Thread(target=fire)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent emit/register raised: {errors}"
