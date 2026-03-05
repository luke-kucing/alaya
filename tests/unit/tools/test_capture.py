"""Unit tests for smart_capture tool."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.capture import (
    smart_capture,
    _detect_person,
    _detect_daily,
    _derive_title,
    _find_matching_note,
    _ensure_daily_note,
)


class TestDetectPerson:
    def test_routes_to_person_note(self, vault: Path) -> None:
        result = smart_capture("had a great 1:1 with alex today", vault)
        assert "people/alex.md" in result
        content = (vault / "people/alex.md").read_text()
        assert "had a great 1:1 with alex today" in content

    def test_case_insensitive(self, vault: Path) -> None:
        assert _detect_person("Met with Alex yesterday", vault) == "people/alex.md"
        assert _detect_person("ALEX is doing great work", vault) == "people/alex.md"

    def test_person_not_found_skips(self, vault: Path) -> None:
        assert _detect_person("talked to zara about the project", vault) is None

    def test_no_people_dir_skips(self, tmp_path: Path) -> None:
        # vault without a people/ directory
        bare_vault = tmp_path / "bare"
        bare_vault.mkdir()
        assert _detect_person("alex said something", bare_vault) is None


class TestDetectDaily:
    def test_daily_triggers(self) -> None:
        assert _detect_daily("today I finished the PR review")
        assert _detect_daily("this morning was productive")
        assert _detect_daily("eod summary: all tasks done")
        assert _detect_daily("standup went well")

    def test_no_trigger(self) -> None:
        assert not _detect_daily("random thought about quantum computing")

    def test_daily_routing(self, vault: Path) -> None:
        result = smart_capture("today I finished the PR review", vault)
        assert "daily/" in result
        assert "daily note" in result


class TestDailyNoteCreation:
    def test_creates_if_missing(self, vault: Path) -> None:
        from datetime import date
        today = date.today().isoformat()
        daily_path = vault / "daily" / f"{today}.md"
        # ensure it doesn't exist yet
        if daily_path.exists():
            daily_path.unlink()

        path = _ensure_daily_note(vault)
        assert (vault / path).exists()
        assert today in path

    def test_returns_existing(self, vault: Path) -> None:
        # 2026-02-25 exists in fixture
        from datetime import date
        today = date.today().isoformat()
        # create today's note first
        path1 = _ensure_daily_note(vault)
        path2 = _ensure_daily_note(vault)
        assert path1 == path2


class TestTopicMatch:
    @patch("alaya.tools.search._hybrid_search_available", return_value=True)
    @patch("alaya.tools.search._run_hybrid_search")
    def test_appends_on_high_score(self, mock_search, mock_avail, vault: Path) -> None:
        mock_search.return_value = [
            {"path": "projects/kubernetes-migration.md", "title": "kubernetes migration", "score": 0.70}
        ]
        result = smart_capture("kubernetes cluster needs more nodes", vault)
        assert "kubernetes-migration.md" in result
        assert "topic match" in result
        content = (vault / "projects/kubernetes-migration.md").read_text()
        assert "kubernetes cluster needs more nodes" in content

    @patch("alaya.tools.search._hybrid_search_available", return_value=True)
    @patch("alaya.tools.search._run_hybrid_search")
    def test_skips_below_threshold(self, mock_search, mock_avail, vault: Path) -> None:
        mock_search.return_value = [
            {"path": "resources/kubernetes-notes.md", "title": "kubernetes notes", "score": 0.40}
        ]
        result = smart_capture("random thought about quantum computing", vault)
        # should fall through to inbox, not match
        assert "Captured" in result


class TestFallbacks:
    def test_fallback_inbox(self, vault: Path) -> None:
        # no person match, no daily trigger, no semantic search
        with patch("alaya.tools.capture._find_matching_note", return_value=None):
            result = smart_capture("random thought about quantum computing", vault)
        assert "Captured" in result
        content = (vault / "inbox.md").read_text()
        assert "random thought about quantum computing" in content

    def test_fallback_create(self, vault: Path) -> None:
        with patch("alaya.tools.capture._find_matching_note", return_value=None):
            result = smart_capture(
                "random thought about quantum computing",
                vault,
                fallback="create",
            )
        assert "Created" in result
        assert "ideas/" in result


class TestVerbatimPreservation:
    def test_text_unchanged_in_file(self, vault: Path) -> None:
        original_text = "alex said: the migration needs 3 more weeks, and we should reconsider the timeline"
        smart_capture(original_text, vault)
        content = (vault / "people/alex.md").read_text()
        assert original_text in content


class TestIntentOverrides:
    def test_intent_person_without_name_match(self, vault: Path) -> None:
        # intent="person" but no person name in text -- falls through to daily/inbox
        # since there's no person match even with intent="person"
        result = smart_capture("discussed capacity planning", vault, intent="person")
        # person detection runs but finds no match, falls through
        assert "daily/" in result or "Captured" in result

    def test_intent_daily_without_trigger(self, vault: Path) -> None:
        result = smart_capture(
            "random observation about architecture",
            vault,
            intent="daily",
        )
        assert "daily/" in result
        assert "daily note" in result


class TestTitleDerivation:
    def test_short_title_from_long_text(self) -> None:
        text = "This is a very long thought about many different things that could go on forever"
        title = _derive_title(text)
        assert len(title.split()) <= 6

    def test_splits_on_sentence(self) -> None:
        text = "First sentence here. Second sentence continues."
        title = _derive_title(text)
        assert "Second" not in title

    def test_empty_text(self) -> None:
        assert _derive_title("") == "untitled"


class TestGracefulFailures:
    def test_index_unavailable_returns_none(self, vault: Path) -> None:
        # _find_matching_note catches all exceptions and returns None
        with patch("alaya.tools.search._hybrid_search_available", side_effect=Exception("boom")):
            result = _find_matching_note("test query", vault)
        assert result is None

    def test_search_error_returns_none(self, vault: Path) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=True):
            with patch("alaya.tools.search._run_hybrid_search", side_effect=Exception("search failed")):
                result = _find_matching_note("test query", vault)
        assert result is None

    def test_search_failure_falls_to_inbox(self, vault: Path) -> None:
        with patch("alaya.tools.capture._find_matching_note", return_value=None):
            result = smart_capture("some random thought", vault)
        assert "Captured" in result
