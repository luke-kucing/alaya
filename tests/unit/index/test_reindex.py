"""Tests for incremental reindex — skip unchanged, re-embed changed, delete removed."""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from alaya.index.reindex import reindex_incremental, reindex_all, reembed_background, ReindexResult


def _make_note(path: Path, text: str = "Body text.") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: Test\ndate: 2026-01-01\n---\n{text}\n")


def _mock_embed(chunks):
    return [np.zeros(768, dtype=np.float32) for _ in chunks]


class TestReindexIncremental:
    def test_first_run_indexes_all_files(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")
        _make_note(vault / "b.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            result = reindex_incremental(vault)

        assert result.notes_indexed == 2
        assert result.notes_skipped == 0

    def test_second_run_skips_unchanged(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)  # first run writes state
            result = reindex_incremental(vault)  # second run: nothing changed

        assert result.notes_indexed == 0
        assert result.notes_skipped == 1

    def test_changed_file_reindexed(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        note = vault / "a.md"
        _make_note(note, "original")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)

        # Change file content (also advances mtime)
        note.write_text("---\ntitle: Test\ndate: 2026-01-01\n---\nupdated content\n")

        embed_calls = []
        def capture_embed(chunks):
            embed_calls.append(chunks)
            return _mock_embed(chunks)

        with patch("alaya.index.reindex.embed_chunks", side_effect=capture_embed):
            result = reindex_incremental(vault)

        assert result.notes_indexed == 1
        assert len(embed_calls) == 1

    def test_deleted_file_removed_from_index(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        note = vault / "a.md"
        _make_note(note)

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)

        note.unlink()

        deleted_paths = []
        def capture_delete(path, store):
            deleted_paths.append(path)

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.reindex.delete_note_from_index", side_effect=capture_delete):
            result = reindex_incremental(vault)

        assert result.notes_deleted == 1
        assert "a.md" in deleted_paths[0]

    def test_state_file_written_to_zk_dir(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)

        state_file = vault / ".zk" / "index_state.json"
        assert state_file.exists()

    def test_result_includes_skipped_and_deleted_counts(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "keep.md")
        _make_note(vault / "gone.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)

        (vault / "gone.md").unlink()

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.reindex.delete_note_from_index"):
            result = reindex_incremental(vault)

        assert result.notes_skipped == 1
        assert result.notes_deleted == 1
        assert result.notes_indexed == 0


class TestModelChangeDetection:
    def test_model_change_forces_full_reindex(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        # First run with model-A
        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.models.get_active_model") as mock_model:
            mock_model.return_value = MagicMock(name="nomic-ai/model-a", dimensions=768)
            mock_model.return_value.name = "model-a"
            reindex_incremental(vault)

        # Verify state file records model-a
        state = json.loads((vault / ".zk" / "index_state.json").read_text())
        assert state["_model"] == "model-a"

        # Second run with model-B — should re-embed everything
        embed_calls = []
        def capture_embed(chunks):
            embed_calls.extend(chunks)
            return _mock_embed(chunks)

        with patch("alaya.index.reindex.embed_chunks", side_effect=capture_embed), \
             patch("alaya.index.models.get_active_model") as mock_model:
            mock_model.return_value = MagicMock(name="nomic-ai/model-b", dimensions=768)
            mock_model.return_value.name = "model-b"
            result = reindex_incremental(vault)

        assert result.notes_indexed == 1  # re-embedded despite no content change
        assert result.notes_skipped == 0

        # State file should now record model-b
        state = json.loads((vault / ".zk" / "index_state.json").read_text())
        assert state["_model"] == "model-b"

    def test_same_model_skips_unchanged(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed):
            reindex_incremental(vault)
            result = reindex_incremental(vault)

        assert result.notes_skipped == 1
        assert result.notes_indexed == 0


class TestReembedBackground:
    def test_reembed_processes_all_notes(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")
        _make_note(vault / "b.md")

        upserted = []
        def capture_upsert(path, chunks, embeddings, store):
            upserted.append(path)

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.reindex.upsert_note", side_effect=capture_upsert), \
             patch("alaya.index.reindex._REEMBED_SLEEP", 0):
            reembed_background(vault, "old-model", "new-model")

        assert len(upserted) == 2

    def test_reembed_updates_health_migration(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        from alaya.index import health
        health.reset()

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.reindex.upsert_note"), \
             patch("alaya.index.reindex._REEMBED_SLEEP", 0):
            reembed_background(vault, "old", "new")

        # Migration should be finished
        status = health.get_status()
        assert status["migration"] is None  # finished

    def test_reembed_writes_state_file(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        _make_note(vault / "a.md")

        with patch("alaya.index.reindex.embed_chunks", side_effect=_mock_embed), \
             patch("alaya.index.reindex.upsert_note"), \
             patch("alaya.index.reindex._REEMBED_SLEEP", 0):
            reembed_background(vault, "old-model", "new-model")

        state = json.loads((vault / ".zk" / "index_state.json").read_text())
        assert state["_model"] == "new-model"
        assert "a.md" in state["files"]
