"""Unit tests for vault_stats tool."""
from pathlib import Path

import pytest

from alaya.tools.stats import vault_stats


class TestVaultStats:
    def test_returns_note_count(self, vault: Path) -> None:
        result = vault_stats(vault)
        assert "note" in result

    def test_lists_directories(self, vault: Path) -> None:
        result = vault_stats(vault)
        assert "Notes by directory:" in result
        # fixture has ideas/ and projects/ directories
        assert "ideas" in result
        assert "projects" in result

    def test_lists_top_tags(self, vault: Path) -> None:
        result = vault_stats(vault)
        # fixture notes have tags; section should appear
        assert "Top tags:" in result

    def test_empty_vault(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty_vault"
        empty.mkdir()
        result = vault_stats(empty)
        assert "empty" in result.lower()

    def test_vault_with_no_tags(self, tmp_path: Path) -> None:
        solo = tmp_path / "solo_vault"
        solo.mkdir()
        note = solo / "note.md"
        note.write_text("---\ntitle: Untagged\ndate: 2026-01-01\n---\nBody.\n")
        result = vault_stats(solo)
        assert "1 note" in result
        assert "Top tags:" not in result
