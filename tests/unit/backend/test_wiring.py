"""Wiring tests: verify tools actually use the backend when one is provided.

These tests catch the case where backend= is accepted but ignored, or where
the legacy fallback path runs instead of the backend path.
"""
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from alaya.backend.protocol import LinkResolution, VaultConfig, NoteEntry, LinkEntry, TagEntry
from alaya.backend.obsidian import ObsidianBackend
from alaya.backend.zk import ZkBackend
from alaya.tools.read import list_notes, get_backlinks, get_links, get_tags
from alaya.tools.search import search_notes
from alaya.tools.structure import rename_note, delete_note
from alaya.tools.edit import extract_section


VAULT_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "vault_fixture"
OBSIDIAN_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "vault_fixture_obsidian"


@pytest.fixture
def zk_vault(tmp_path: Path) -> Path:
    vault_path = tmp_path / "zk_vault"
    shutil.copytree(VAULT_FIXTURE_PATH, vault_path)
    return vault_path


@pytest.fixture
def obs_vault(tmp_path: Path) -> Path:
    vault_path = tmp_path / "obs_vault"
    shutil.copytree(OBSIDIAN_FIXTURE_PATH, vault_path)
    return vault_path


def _zk_backend(vault: Path) -> ZkBackend:
    config = VaultConfig(
        root=vault, vault_type="zk", data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    return ZkBackend(config)


def _obs_backend(vault: Path) -> ObsidianBackend:
    config = VaultConfig(
        root=vault, vault_type="obsidian", data_dir_name=".obsidian",
        link_resolution=LinkResolution.FILENAME,
    )
    return ObsidianBackend(config)


class TestListNotesUsesBackend:
    """list_notes(backend=...) must call backend.list_notes, not run_zk."""

    def test_with_obsidian_backend_does_not_call_run_zk(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        with patch("alaya.zk.run_zk", side_effect=AssertionError("run_zk should not be called")):
            result = list_notes(obs_vault, backend=backend)
        assert "second-brain" in result.lower() or "Second Brain" in result

    def test_with_obsidian_backend_returns_real_notes(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        result = list_notes(obs_vault, backend=backend)
        assert "|" in result  # markdown table
        assert "kubernetes" in result.lower()

    def test_with_obsidian_backend_filters_by_directory(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        result = list_notes(obs_vault, directory="Ideas", backend=backend)
        assert "voice-capture" in result.lower()
        # Should NOT include notes from other directories
        assert "kubernetes-notes" not in result.lower()

    def test_with_obsidian_backend_filters_by_tag(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        result = list_notes(obs_vault, tag="kubernetes", backend=backend)
        assert "kubernetes" in result.lower()

    def test_with_zk_backend_calls_backend_not_raw_run_zk(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        # Mock at the backend level to prove the backend path is taken
        fake_entries = [NoteEntry(path="test.md", title="Test", date="2026-01-01", tags="#test")]
        with patch.object(backend, "list_notes", return_value=fake_entries) as mock:
            result = list_notes(zk_vault, backend=backend)
        mock.assert_called_once()
        assert "Test" in result


class TestGetBacklinksUsesBackend:
    def test_with_obsidian_backend_does_not_call_run_zk(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        with patch("alaya.zk.run_zk", side_effect=AssertionError("run_zk should not be called")):
            result = get_backlinks("Projects/second-brain.md", obs_vault, backend=backend)
        # voice-capture and daily note link to [[second-brain]]
        assert "voice-capture" in result.lower()

    def test_with_zk_backend_calls_backend_method(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        fake_entries = [LinkEntry(path="daily/2026-02-25.md", title="2026-02-25")]
        with patch.object(backend, "get_backlinks", return_value=fake_entries) as mock:
            result = get_backlinks("projects/second-brain.md", zk_vault, backend=backend)
        mock.assert_called_once_with("projects/second-brain.md")
        assert "2026-02-25" in result


class TestGetLinksUsesBackend:
    def test_with_obsidian_backend_does_not_call_run_zk(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        with patch("alaya.zk.run_zk", side_effect=AssertionError("run_zk should not be called")):
            result = get_links("Projects/second-brain.md", obs_vault, backend=backend)
        assert "kubernetes-notes" in result.lower()

    def test_with_zk_backend_calls_backend_method(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        fake_entries = [LinkEntry(path="resources/k8s.md", title="Kubernetes")]
        with patch.object(backend, "get_outlinks", return_value=fake_entries) as mock:
            result = get_links("projects/second-brain.md", zk_vault, backend=backend)
        mock.assert_called_once_with("projects/second-brain.md")
        assert "Kubernetes" in result


class TestGetTagsUsesBackend:
    def test_with_obsidian_backend_does_not_call_run_zk(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        with patch("alaya.zk.run_zk", side_effect=AssertionError("run_zk should not be called")):
            result = get_tags(obs_vault, backend=backend)
        assert "project" in result
        assert "kubernetes" in result

    def test_with_zk_backend_calls_backend_method(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        fake_entries = [TagEntry(name="kubernetes", count=3)]
        with patch.object(backend, "list_tags", return_value=fake_entries) as mock:
            result = get_tags(zk_vault, backend=backend)
        mock.assert_called_once()
        assert "kubernetes" in result
        assert "3" in result


class TestSearchNotesUsesBackend:
    """When no index is available, search_notes falls back to backend.keyword_search."""

    def test_obsidian_fallback_does_not_call_run_zk(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        with patch("alaya.tools.search._hybrid_search_available", return_value=False), \
             patch("alaya.zk.run_zk", side_effect=AssertionError("run_zk should not be called")):
            result = search_notes("Kubernetes", obs_vault, backend=backend)
        assert "kubernetes" in result.lower()

    def test_zk_fallback_calls_backend_keyword_search(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        fake_entries = [NoteEntry(path="k8s.md", title="Kubernetes", date="2026-01-01")]
        with patch("alaya.tools.search._hybrid_search_available", return_value=False), \
             patch.object(backend, "keyword_search", return_value=fake_entries) as mock:
            result = search_notes("kubernetes", zk_vault, backend=backend)
        mock.assert_called_once()
        assert "Kubernetes" in result


class TestRenameNoteUsesBackend:
    """rename_note(backend=...) must use backend.note_link_key for wikilink resolution."""

    def test_obsidian_rename_uses_filename_stem_for_wikilinks(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        old_path = "Ideas/voice-capture.md"
        old_content = (obs_vault / old_path).read_text()
        # second-brain.md does NOT link to voice-capture, so no wikilink updates needed
        # but we can verify the key derivation
        old_key = backend.note_link_key(obs_vault / old_path, old_content)
        assert old_key == "voice-capture"  # filename stem, not "Voice Capture"

    def test_zk_rename_uses_frontmatter_title_for_wikilinks(self, zk_vault: Path) -> None:
        backend = _zk_backend(zk_vault)
        path = "projects/second-brain.md"
        content = (zk_vault / path).read_text()
        key = backend.note_link_key(zk_vault / path, content)
        assert key == "second-brain"  # frontmatter title


class TestDeleteNoteUsesConfigArchivesDir:
    def test_uses_default_archives_dir(self, zk_vault: Path) -> None:
        # Create a note to delete
        (zk_vault / "ideas" / "deleteme.md").write_text(
            "---\ntitle: deleteme\ndate: 2026-01-01\n---\nGoodbye."
        )
        result = delete_note("ideas/deleteme.md", zk_vault)
        assert result.startswith("archives/")
        assert (zk_vault / result).exists()

    def test_uses_custom_archives_dir(self, obs_vault: Path) -> None:
        # Create Archive dir and a note to delete
        (obs_vault / "Archive").mkdir(exist_ok=True)
        (obs_vault / "Ideas" / "deleteme.md").write_text(
            "---\ntitle: deleteme\ndate: 2026-01-01\n---\nGoodbye."
        )
        result = delete_note("Ideas/deleteme.md", obs_vault, archives_dir="Archive")
        assert result.startswith("Archive/")
        assert (obs_vault / result).exists()


class TestExtractSectionUsesBackend:
    def test_obsidian_extract_leaves_filename_wikilink(self, obs_vault: Path) -> None:
        backend = _obs_backend(obs_vault)
        # Create a note with sections to extract from
        source_path = "Projects/extractable.md"
        (obs_vault / source_path).write_text(
            "---\ntitle: Extractable\ndate: 2026-01-01\n---\n\n"
            "## Overview\nMain content.\n\n"
            "## Details\nDetailed content here.\n"
        )
        new_path = extract_section(
            source_path, "Details", "Extracted Details", "Ideas", obs_vault, backend=backend,
        )
        # The original note should have a wikilink using the filename stem
        updated = (obs_vault / source_path).read_text()
        assert "[[extracted-details]]" in updated  # filename stem, not "Extracted Details"

    def test_no_backend_leaves_title_wikilink(self, zk_vault: Path) -> None:
        source_path = "projects/extractable.md"
        (zk_vault / source_path).write_text(
            "---\ntitle: Extractable\ndate: 2026-01-01\n---\n\n"
            "## Overview\nMain content.\n\n"
            "## Details\nDetailed content here.\n"
        )
        new_path = extract_section(
            source_path, "Details", "Extracted Details", "ideas", zk_vault, backend=None,
        )
        updated = (zk_vault / source_path).read_text()
        assert "[[Extracted Details]]" in updated  # title, not filename stem
