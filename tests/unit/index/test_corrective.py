"""Tests for corrective RAG: quality check and query reformulation."""
from alaya.index.corrective import needs_correction, filter_relevant, reformulate_query


class TestNeedsCorrection:
    def test_empty_results_need_correction(self):
        assert needs_correction([]) is True

    def test_low_score_needs_correction(self):
        results = [{"score": 0.1, "path": "a.md"}]
        assert needs_correction(results) is True

    def test_high_score_does_not_need_correction(self):
        results = [{"score": 0.8, "path": "a.md"}]
        assert needs_correction(results) is False

    def test_threshold_boundary(self):
        assert needs_correction([{"score": 0.3}]) is False
        assert needs_correction([{"score": 0.29}]) is True

    def test_custom_threshold(self):
        results = [{"score": 0.5}]
        assert needs_correction(results, min_score=0.6) is True
        assert needs_correction(results, min_score=0.4) is False


class TestFilterRelevant:
    def test_removes_low_scores(self):
        results = [
            {"score": 0.8, "path": "a.md"},
            {"score": 0.1, "path": "b.md"},
            {"score": 0.5, "path": "c.md"},
        ]
        filtered = filter_relevant(results)
        assert len(filtered) == 2
        assert all(r["score"] >= 0.2 for r in filtered)

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
