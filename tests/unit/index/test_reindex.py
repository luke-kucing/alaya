"""Tests for incremental reindex — skip unchanged, re-embed changed, delete removed."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from alaya.index.reindex import reindex_incremental, reindex_all, ReindexResult


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
