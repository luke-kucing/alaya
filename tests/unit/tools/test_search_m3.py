"""M3 additions to search: hybrid path, reindex_vault."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from alaya.tools.search import search_notes
from alaya.tools.read import reindex_vault


class TestSearchNotesHybrid:
    def test_uses_hybrid_search_when_index_available(self, vault: Path, tmp_path: Path) -> None:
        mock_results = [
            {"path": "resources/kubernetes-notes.md", "title": "kubernetes-notes",
             "directory": "resources", "score": 0.92},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_hybrid_search", return_value=mock_results):
            result = search_notes("kubernetes", vault)
        assert "kubernetes-notes" in result
        assert "0.9" in result  # relevance score

    def test_falls_back_to_zk_when_no_index(self, vault: Path) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=False), \
             patch("alaya.tools.search.run_zk", return_value="resources/kubernetes-notes.md\tkubernetes-notes\t2026-02-01"):
            result = search_notes("kubernetes", vault)
        assert "kubernetes-notes" in result

    def test_result_includes_relevance_score_when_hybrid(self, vault: Path) -> None:
        mock_results = [
            {"path": "resources/kubernetes-notes.md", "title": "kubernetes-notes",
             "directory": "resources", "score": 0.87},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_hybrid_search", return_value=mock_results):
            result = search_notes("kubernetes", vault)
        assert "0.87" in result


class TestReindexVault:
    def test_requires_confirm(self, vault: Path) -> None:
        result = reindex_vault(vault, confirm=False)
        assert "confirm" in result.lower()

    def test_returns_stats_on_success(self, vault: Path) -> None:
        mock_result = MagicMock()
        mock_result.notes_indexed = 12
        mock_result.chunks_created = 47
        mock_result.duration_seconds = 3.2

        with patch("alaya.tools.read._run_reindex", return_value=mock_result):
            result = reindex_vault(vault, confirm=True)

        assert "12" in result
        assert "47" in result

    def test_reindex_error_returns_message(self, vault: Path) -> None:
        with patch("alaya.tools.read._run_reindex", side_effect=Exception("disk full")):
            result = reindex_vault(vault, confirm=True)
        assert "error" in result.lower() or "failed" in result.lower()
