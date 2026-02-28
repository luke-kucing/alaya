"""Unit tests for structure tools: move_note, rename_note, delete_note, find_references."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.structure import move_note, rename_note, delete_note, find_references


class TestMoveNote:
    def test_file_moved_to_new_directory(self, vault: Path) -> None:
        move_note("ideas/voice-capture.md", "projects", vault)
        assert not (vault / "ideas/voice-capture.md").exists()
        assert (vault / "projects/voice-capture.md").exists()

    def test_returns_new_path(self, vault: Path) -> None:
        new_path = move_note("ideas/voice-capture.md", "projects", vault)
        assert new_path == "projects/voice-capture.md"

    def test_source_missing_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            move_note("ideas/ghost.md", "projects", vault)

    def test_invalid_destination_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            move_note("ideas/voice-capture.md", "../../etc", vault)

    def test_wikilinks_unchanged_after_move(self, vault: Path) -> None:
        # zk uses title-based wikilinks ([[title]]). Moving a file changes its
        # directory but not its title, so existing wikilinks remain valid.
        note = vault / "projects/second-brain.md"
        note.write_text(note.read_text() + "\n- [[voice-capture]]\n")

        move_note("ideas/voice-capture.md", "resources", vault)

        # [[voice-capture]] is still valid — the title hasn't changed
        assert "[[voice-capture]]" in note.read_text()
        # the file itself is at the new location
        assert (vault / "resources/voice-capture.md").exists()

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            move_note("../../etc/passwd", "projects", vault)


class TestRenameNote:
    def test_file_renamed(self, vault: Path) -> None:
        rename_note("ideas/voice-capture.md", "audio-capture", vault)
        assert not (vault / "ideas/voice-capture.md").exists()
        assert (vault / "ideas/audio-capture.md").exists()

    def test_frontmatter_title_updated(self, vault: Path) -> None:
        rename_note("ideas/voice-capture.md", "audio-capture", vault)
        content = (vault / "ideas/audio-capture.md").read_text()
        assert "title: audio-capture" in content

    def test_returns_new_path(self, vault: Path) -> None:
        new_path = rename_note("ideas/voice-capture.md", "audio-capture", vault)
        assert new_path == "ideas/audio-capture.md"

    def test_wikilinks_updated_vault_wide(self, vault: Path) -> None:
        # plant a wikilink in another note
        ref = vault / "projects/second-brain.md"
        ref.write_text(ref.read_text() + "\n- [[voice-capture]]\n")

        rename_note("ideas/voice-capture.md", "audio-capture", vault)

        content = ref.read_text()
        assert "[[audio-capture]]" in content
        assert "[[voice-capture]]" not in content

    def test_source_missing_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            rename_note("ideas/ghost.md", "something", vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            rename_note("../../etc/passwd", "new", vault)


class TestDeleteNote:
    def test_moves_to_archives(self, vault: Path) -> None:
        delete_note("ideas/voice-capture.md", vault)
        assert not (vault / "ideas/voice-capture.md").exists()
        assert (vault / "archives/voice-capture.md").exists()

    def test_returns_archive_path(self, vault: Path) -> None:
        result = delete_note("ideas/voice-capture.md", vault)
        assert result == "archives/voice-capture.md"

    def test_reason_appended_to_note(self, vault: Path) -> None:
        delete_note("ideas/voice-capture.md", vault, reason="superseded by voice-pipeline project")
        content = (vault / "archives/voice-capture.md").read_text()
        assert "superseded by voice-pipeline project" in content

    def test_already_archived_raises(self, vault: Path) -> None:
        # first delete
        delete_note("ideas/voice-capture.md", vault)
        # second delete should fail
        with pytest.raises(ValueError, match="already archived"):
            delete_note("archives/voice-capture.md", vault)

    def test_source_missing_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            delete_note("ideas/ghost.md", vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            delete_note("../../etc/passwd", vault)


class TestFindReferences:
    def test_finds_wikilink_references(self, vault: Path) -> None:
        # plant a known wikilink
        ref = vault / "projects/second-brain.md"
        ref.write_text(ref.read_text() + "\n- [[voice-capture]]\n")

        results = find_references("voice-capture", vault)
        paths = [r["path"] for r in results]
        assert any("second-brain" in p for p in paths)

    def test_returns_list_of_dicts(self, vault: Path) -> None:
        results = find_references("second-brain", vault)
        assert isinstance(results, list)
        for r in results:
            assert "path" in r
            assert "type" in r

    def test_no_references_returns_empty_list(self, vault: Path) -> None:
        results = find_references("absolutelyuniquetitlexyz", vault)
        assert results == []

    def test_text_mentions_included_when_requested(self, vault: Path) -> None:
        # plant a text mention (not a wikilink)
        ref = vault / "projects/second-brain.md"
        ref.write_text(ref.read_text() + "\nThis mentions voice-capture as plain text.\n")

        results = find_references("voice-capture", vault, include_text_mentions=True)
        types = {r["type"] for r in results}
        assert "text" in types
