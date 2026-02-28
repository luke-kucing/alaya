"""Tests for the event system used by write-through index updates."""
import pytest

from alaya.events import on_note_change, emit, clear_listeners


class TestEventSystem:
    def setup_method(self):
        clear_listeners()

    def test_emit_calls_registered_listener(self):
        received = []
        on_note_change(lambda event, path: received.append((event, path)))
        emit("created", "notes/test.md")
        assert received == [("created", "notes/test.md")]

    def test_multiple_listeners_all_called(self):
        calls_a, calls_b = [], []
        on_note_change(lambda e, p: calls_a.append((e, p)))
        on_note_change(lambda e, p: calls_b.append((e, p)))
        emit("modified", "notes/foo.md")
        assert calls_a == [("modified", "notes/foo.md")]
        assert calls_b == [("modified", "notes/foo.md")]

    def test_clear_listeners(self):
        received = []
        on_note_change(lambda e, p: received.append(e))
        clear_listeners()
        emit("created", "notes/test.md")
        assert received == []

    def test_no_listeners_does_not_raise(self):
        emit("deleted", "notes/gone.md")  # should not raise


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
