"""Tests for adaptive query routing."""
from datetime import date, timedelta

from alaya.index.router import classify_query, QueryStrategy


class TestClassifyQuery:
    def test_empty_query_returns_hybrid(self):
        result = classify_query("")
        assert result.strategy == QueryStrategy.HYBRID

    def test_single_word_returns_keyword(self):
        result = classify_query("kubernetes")
        assert result.strategy == QueryStrategy.KEYWORD

    def test_two_words_returns_keyword(self):
        result = classify_query("helm charts")
        assert result.strategy == QueryStrategy.KEYWORD

    def test_question_returns_semantic(self):
        result = classify_query("what is the deployment strategy for kubernetes?")
        assert result.strategy == QueryStrategy.SEMANTIC

    def test_how_question_returns_semantic(self):
        result = classify_query("how do I set up argocd?")
        assert result.strategy == QueryStrategy.SEMANTIC

    def test_longer_phrase_returns_hybrid(self):
        result = classify_query("kubernetes deployment best practices production")
        assert result.strategy == QueryStrategy.HYBRID

    def test_today_returns_temporal(self):
        result = classify_query("what did I work on today")
        assert result.strategy == QueryStrategy.TEMPORAL
        assert result.since == date.today().isoformat()

    def test_yesterday_returns_temporal(self):
        result = classify_query("notes from yesterday")
        assert result.strategy == QueryStrategy.TEMPORAL
        expected = (date.today() - timedelta(days=1)).isoformat()
        assert result.since == expected

    def test_last_week_returns_temporal(self):
        result = classify_query("meetings last week")
        assert result.strategy == QueryStrategy.TEMPORAL
        expected = (date.today() - timedelta(days=7)).isoformat()
        assert result.since == expected

    def test_recently_returns_temporal(self):
        result = classify_query("recently modified notes")
        assert result.strategy == QueryStrategy.TEMPORAL
        expected = (date.today() - timedelta(days=14)).isoformat()
        assert result.since == expected

    def test_explicit_since_date_returns_temporal(self):
        result = classify_query("kubernetes since 2026-01-15")
        assert result.strategy == QueryStrategy.TEMPORAL
        assert result.since == "2026-01-15"
        assert "since" not in result.query.lower() or "2026" not in result.query

    def test_this_month_returns_temporal(self):
        result = classify_query("this month standup notes")
        assert result.strategy == QueryStrategy.TEMPORAL
        expected = (date.today() - timedelta(days=30)).isoformat()
        assert result.since == expected

    def test_preserves_query_text(self):
        result = classify_query("kubernetes")
        assert result.query == "kubernetes"

    def test_question_preserves_full_text(self):
        result = classify_query("what meetings did I have?")
        assert result.query == "what meetings did I have?"
