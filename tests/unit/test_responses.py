"""Unit tests for response shaping: token counts and output caps."""
import pytest

from alaya import responses
from alaya.responses import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    annotate,
    cap,
    get_max_output_tokens,
    has_token_count,
    shape,
)
from alaya.tokens import count_tokens


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", raising=False)


class TestMaxOutputTokens:
    def test_default(self) -> None:
        assert get_max_output_tokens() == DEFAULT_MAX_OUTPUT_TOKENS

    def test_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "500")
        assert get_max_output_tokens() == 500

    def test_zero_disables(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "0")
        assert get_max_output_tokens() == 0

    def test_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "lots")
        assert get_max_output_tokens() == DEFAULT_MAX_OUTPUT_TOKENS


class TestAnnotate:
    def test_appends_token_count(self) -> None:
        out = annotate("hello world")
        assert "<!-- token_count:" in out
        assert out.startswith("hello world")

    def test_does_not_double_annotate(self) -> None:
        once = annotate("hello")
        assert annotate(once) == once

    def test_recognises_an_existing_count_with_extra_fields(self) -> None:
        assert has_token_count("body\n\n<!-- token_count: 12; sources: 3 -->")

    def test_count_is_plausible(self) -> None:
        text = "word " * 100
        out = annotate(text)
        reported = int(out.split("token_count:")[1].split("-->")[0].strip())
        assert reported == count_tokens(text)


class TestCap:
    def test_short_text_is_untouched(self) -> None:
        out, truncated = cap("short")
        assert out == "short"
        assert truncated is False

    def test_long_text_is_truncated_with_a_footer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        out, truncated = cap("word " * 2000)
        assert truncated is True
        assert "tokens truncated" in out
        assert count_tokens(out) <= 200

    def test_hint_is_included(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        out, _ = cap("word " * 2000, hint="lower limit")
        assert "lower limit" in out

    def test_cap_disabled_by_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "0")
        text = "word " * 5000
        out, truncated = cap(text)
        assert out == text
        assert truncated is False


class TestShape:
    def test_caps_and_annotates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        out = shape("word " * 2000)
        assert "token_count:" in out
        assert "truncated" in out
        assert count_tokens(out) <= 200 + 60

    def test_unbounded_skips_the_cap_but_still_annotates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        out = shape("word " * 2000, unbounded=True)
        assert "truncated" not in out
        assert "token_count:" in out

    def test_non_string_passes_through(self) -> None:
        assert shape(None) is None
        assert shape(42) == 42

    def test_preserves_an_existing_token_count(self) -> None:
        body = "already counted\n\n<!-- token_count: 3; sources: 1 -->"
        assert shape(body) == body
