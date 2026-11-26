"""Tests for corrective RAG: quality check and query reformulation."""
from pathlib import Path
from unittest.mock import patch

from alaya.index.corrective import filter_relevant, reformulate_query


class TestFilterRelevant:
    def test_removes_low_scores(self):
        results = [
            {"score": 0.8, "path": "a.md"},
            {"score": 0.1, "path": "b.md"},
            {"score": 0.5, "path": "c.md"},
        ]
        filtered = filter_relevant(results, threshold=0.2)
        assert len(filtered) == 2
        assert all(r["score"] >= 0.2 for r in filtered)

    def test_default_keeps_low_positive_scores(self):
        # #190: low hybrid scores are still candidates; only negatives are dropped.
        results = [{"score": 0.05}, {"score": 0.0}, {"score": -0.1}]
        assert filter_relevant(results) == [{"score": 0.05}, {"score": 0.0}]

    def test_keeps_all_above_threshold(self):
        results = [{"score": 0.5}, {"score": 0.3}]
        assert len(filter_relevant(results)) == 2

    def test_empty_input(self):
        assert filter_relevant([]) == []


class TestReformulateQuery:
    def test_strips_question_words(self):
        alts = reformulate_query("what is the deployment strategy?")
        assert any("deployment strategy" in a for a in alts)

    def test_drops_filler_words(self):
        alts = reformulate_query("notes about the kubernetes deployment in production")
        # should produce a version without "about", "the", "in"
        assert any("kubernetes" in a and "about" not in a for a in alts)

    def test_short_query_returns_alternatives(self):
        alts = reformulate_query("how does argocd work?")
        assert len(alts) >= 1
        assert any("argocd" in a for a in alts)

    def test_single_word_returns_empty(self):
        # Can't reformulate further
        alts = reformulate_query("kubernetes")
        # The stripped version equals the input, so it's excluded
        assert all(a.lower() != "kubernetes" for a in alts)

    def test_long_query_produces_shortened_version(self):
        alts = reformulate_query("what are the best practices for kubernetes deployment in production environments")
        assert any(len(a.split()) <= 4 for a in alts)


class TestCorrectiveSearch:
    """Reformulations only run when the original query finds nothing (LongMemEval: they
    used to replace good results, e.g. "airline ... March and April?" -> "March and April?")."""

    def _run(self, by_query):
        from alaya.tools.search import _run_corrective_search
        with patch("alaya.tools.search._run_routed_search", side_effect=lambda q, *a, **k: by_query.get(q, [])) as m:
            return _run_corrective_search("Which airline did I fly with the most in March and April?", Path(".")), m

    def test_keeps_non_empty_results_even_with_low_scores(self):
        hit = [{"path": "flights.md", "score": 0.02}]
        out, m = self._run({"Which airline did I fly with the most in March and April?": hit,
                            "March and April?": [{"path": "calendar.md", "score": 0.9}]})
        assert out == hit and m.call_count == 1

    def test_retries_reformulations_when_empty(self):
        hit = [{"path": "flights.md", "score": 0.1}]
        out, _ = self._run({"airline did I fly with the most in March and April": hit})
        assert out == hit


class TestTemporalFallback:
    def test_empty_inferred_window_falls_back_to_unfiltered(self):
        from alaya.tools.search import _run_routed_search
        hit = [{"path": "old.md", "score": 0.5}]
        with patch("alaya.index.store.get_store"), \
             patch("alaya.index.embedder.embed_query"), \
             patch("alaya.index.store.hybrid_search", side_effect=lambda *a, since=None, **k: [] if since else hit) as m:
            assert _run_routed_search("What certification did I complete last month?", Path(".")) == hit
        assert [c.kwargs["since"] for c in m.call_args_list][-1] is None and m.call_args_list[0].kwargs["since"]

    def test_explicit_since_is_respected(self):
        from alaya.tools.search import _run_routed_search
        with patch("alaya.index.store.get_store"), \
             patch("alaya.index.embedder.embed_query"), \
             patch("alaya.index.store.hybrid_search", return_value=[]) as m:
            assert _run_routed_search("What did I complete last month?", Path("."), since="2026-01-01") == []
        assert m.call_count == 1
