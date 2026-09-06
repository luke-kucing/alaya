"""Unit tests for token counting and budget truncation."""
import pytest

from alaya import tokens


@pytest.fixture(autouse=True)
def _reset_encoder():
    tokens.reset_encoder()
    yield
    tokens.reset_encoder()


class TestCountTokens:
    def test_empty_string_is_zero(self) -> None:
        assert tokens.count_tokens("") == 0

    def test_longer_text_counts_more(self) -> None:
        short = tokens.count_tokens("one two three")
        long = tokens.count_tokens("one two three " * 50)
        assert long > short

    def test_fallback_used_when_tiktoken_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tokens, "_get_encoder", lambda: None)
        assert tokens.count_tokens("a b c d") > 0


class TestTruncateToTokens:
    def test_under_budget_is_unchanged(self) -> None:
        text = "short text"
        out, truncated = tokens.truncate_to_tokens(text, 1000)
        assert out == text
        assert truncated is False

    def test_over_budget_is_cut_and_flagged(self) -> None:
        text = "word " * 500
        out, truncated = tokens.truncate_to_tokens(text, 50)
        assert truncated is True
        assert tokens.count_tokens(out) <= 50
        assert len(out) < len(text)

    def test_zero_budget_returns_empty(self) -> None:
        out, truncated = tokens.truncate_to_tokens("anything", 0)
        assert out == ""
        assert truncated is True

    def test_prefers_line_boundary(self) -> None:
        text = "\n".join(f"line {i} with some filler words here" for i in range(200))
        out, truncated = tokens.truncate_to_tokens(text, 60)
        assert truncated is True
        # Cut on a line boundary, so no partial trailing line.
        assert not out.endswith(" ")

    def test_fallback_respects_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(tokens, "_get_encoder", lambda: None)
        out, truncated = tokens.truncate_to_tokens("word " * 500, 40)
        assert truncated is True
        assert tokens.count_tokens(out) <= 40
