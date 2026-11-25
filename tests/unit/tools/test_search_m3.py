"""M3 additions to search: hybrid path, reindex_vault."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from alaya.tools.search import search_notes
from alaya.tools.read import reindex_vault


class TestSearchNotesHybrid:
    def test_uses_routed_search_when_index_available(self, vault: Path, tmp_path: Path) -> None:
        mock_results = [
            {"path": "resources/kubernetes-notes.md", "title": "kubernetes-notes",
             "directory": "resources", "score": 0.92},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=mock_results):
            result = search_notes("kubernetes", vault)
        assert "kubernetes-notes" in result
        assert "0.9" in result  # relevance score

    def test_falls_back_to_zk_when_no_index(self, vault: Path) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=False), \
             patch("alaya.zk.run_zk", return_value="resources/kubernetes-notes.md\tkubernetes-notes\t2026-02-01"):
            result = search_notes("kubernetes", vault)
        assert "kubernetes-notes" in result

    def test_result_includes_relevance_score_when_hybrid(self, vault: Path) -> None:
        mock_results = [
            {"path": "resources/kubernetes-notes.md", "title": "kubernetes-notes",
             "directory": "resources", "score": 0.87},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=mock_results):
            result = search_notes("kubernetes", vault)
        assert "0.87" in result


class TestSearchSnippets:
    """#145: indexed hits carry chunk text so agents can ground without get_note."""

    def _search(self, vault: Path, results: list[dict]) -> str:
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=results):
            return search_notes("q", vault)

    def test_snippet_column_is_flat_and_table_safe(self, vault: Path) -> None:
        out = self._search(vault, [{"title": "T", "path": "a.md", "score": 0.9,
                                    "text": "line one\n\n  a | b"}])
        assert "| Title | Path | Score | Snippet |" in out
        assert out.splitlines()[-1].endswith("| line one a \\| b |")

    def test_context_prefix_is_stripped(self, vault: Path) -> None:
        from alaya.index.embedder import chunk_note

        content = (vault / "projects/second-brain.md").read_text()
        chunk = chunk_note("projects/second-brain.md", content)[0]  # as indexed
        assert chunk.text.startswith("From note:")
        out = self._search(vault, [{"title": "T", "path": "a.md", "score": 0.9, "text": chunk.text}])
        assert "From note:" not in out

    def test_long_chunk_is_truncated(self, vault: Path) -> None:
        from alaya.tools.search import SNIPPET_CHARS

        out = self._search(vault, [{"title": "T", "path": "a.md", "score": 0.9, "text": "w " * 1000}])
        snippet = out.splitlines()[-1].split(" | ")[-1]
        assert snippet.endswith("… |") and len(snippet) <= SNIPPET_CHARS + 4

    def test_graph_expanded_hit_without_text(self, vault: Path) -> None:
        out = self._search(vault, [{"title": "T", "path": "a.md", "score": 0.5}])
        assert out.splitlines()[-1] == "| [[T]] | `a.md` | 0.50 |  |"


class TestReindexVault:
    def test_requires_confirm(self, vault: Path) -> None:
        result = reindex_vault(vault, confirm=False)
        assert "confirm" in result.lower()

    def test_returns_stats_on_success(self, vault: Path) -> None:
        mock_result = MagicMock()
        mock_result.notes_indexed = 12
        mock_result.chunks_created = 47
        mock_result.duration_seconds = 3.2
        mock_result.notes_skipped = 5
        mock_result.notes_deleted = 0

        with patch("alaya.index.reindex.reindex_incremental", return_value=mock_result):
            result = reindex_vault(vault, confirm=True)

        assert "12" in result
        assert "47" in result

    def test_reindex_error_returns_message(self, vault: Path) -> None:
        with patch("alaya.index.reindex.reindex_incremental", side_effect=Exception("disk full")):
            result = reindex_vault(vault, confirm=True)
        assert "error" in result.lower() or "failed" in result.lower()
