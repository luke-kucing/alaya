"""Unit tests for search tools (M1: zk keyword fallback only)."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.search import search_notes


ZK_SEARCH_OUTPUT = """\
projects/second-brain.md\tsecond-brain\t2026-02-23
resources/kubernetes-notes.md\tkubernetes-notes\t2026-02-01
"""


class TestSearchNotes:
    def test_returns_results_for_keyword(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()):
            result = search_notes("kubernetes", vault)
        assert "kubernetes-notes" in result
        assert "second-brain" in result

    def test_no_results_returns_message(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=""):
            result = search_notes("xyznotfound", vault)
        assert "no notes" in result.lower() or "no results" in result.lower()

    def test_passes_query_to_zk(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value="") as mock_zk:
            search_notes("helm charts", vault)
        args = mock_zk.call_args[0][0]
        assert any("helm charts" in a for a in args)

    def test_filter_by_directory(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()) as mock_zk:
            search_notes("kubernetes", vault, directory="resources")
        args = mock_zk.call_args[0][0]
        assert "resources" in args

    def test_returns_markdown(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()):
            result = search_notes("kubernetes", vault)
        assert isinstance(result, str)
        assert "|" in result  # markdown table

    # --- tags and since filters (R-SQ-02) ---

    def test_filter_by_tag_passes_tag_to_zk(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()) as mock_zk:
            search_notes("kubernetes", vault, tags=["kubernetes"])
        args = mock_zk.call_args[0][0]
        assert "--tag" in args
        assert "kubernetes" in args

    def test_filter_by_multiple_tags(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()) as mock_zk:
            search_notes("notes", vault, tags=["kubernetes", "reference"])
        args = mock_zk.call_args[0][0]
        # each tag should appear after --tag
        assert args.count("--tag") == 2

    def test_since_passes_modified_after_to_zk(self, vault: Path) -> None:
        with patch("alaya.tools.search.run_zk", return_value=ZK_SEARCH_OUTPUT.strip()) as mock_zk:
            search_notes("notes", vault, since="2026-01-01")
        args = mock_zk.call_args[0][0]
        assert "--modified-after" in args
        assert "2026-01-01" in args
