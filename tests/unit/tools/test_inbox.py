"""Unit tests for inbox tools."""
from pathlib import Path

import pytest

from alaya.tools.inbox import capture_to_inbox, get_inbox, clear_inbox_item


class TestCaptureToInbox:
    def test_appends_timestamped_entry(self, vault: Path) -> None:
        capture_to_inbox("check on the deploy pipeline", vault)
        content = (vault / "inbox.md").read_text()
        assert "check on the deploy pipeline" in content

    def test_entry_has_timestamp(self, vault: Path) -> None:
        capture_to_inbox("timestamped entry", vault)
        content = (vault / "inbox.md").read_text()
        # should have a date prefix like "2026-"
        lines = [l for l in content.splitlines() if "timestamped entry" in l]
        assert lines
        assert "2026-" in lines[0]

    def test_original_entries_preserved(self, vault: Path) -> None:
        original = (vault / "inbox.md").read_text()
        capture_to_inbox("new item", vault)
        content = (vault / "inbox.md").read_text()
        # all original lines still present
        for line in original.splitlines():
            assert line in content

    def test_returns_confirmation_string(self, vault: Path) -> None:
        result = capture_to_inbox("confirm this", vault)
        assert isinstance(result, str)
        assert "confirm this" in result


class TestGetInbox:
    def test_returns_inbox_content(self, vault: Path) -> None:
        result = get_inbox(vault)
        # fixture has 6 items
        assert "vector search" in result
        assert "alex" in result

    def test_returns_string(self, vault: Path) -> None:
        result = get_inbox(vault)
        assert isinstance(result, str)

    def test_empty_inbox_returns_message(self, vault: Path) -> None:
        # overwrite inbox with header only
        (vault / "inbox.md").write_text("# Inbox\n\nQuick capture. Process weekly.\n")
        result = get_inbox(vault)
        assert "empty" in result.lower() or "no items" in result.lower()


class TestClearInboxItem:
    def test_removes_matching_line(self, vault: Path) -> None:
        target = "look into vector search options for the project"
        clear_inbox_item(target, vault)
        content = (vault / "inbox.md").read_text()
        assert target not in content

    def test_other_lines_preserved(self, vault: Path) -> None:
        target = "look into vector search options for the project"
        clear_inbox_item(target, vault)
        content = (vault / "inbox.md").read_text()
        assert "alex mentioned wanting more ownership" in content

    def test_no_match_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            clear_inbox_item("this item does not exist", vault)
