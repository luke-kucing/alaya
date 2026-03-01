"""Unit tests for structured error codes."""
from alaya.errors import error, NOT_FOUND, ALREADY_EXISTS, OUTSIDE_VAULT, SECTION_NOT_FOUND


def test_error_format() -> None:
    result = error(NOT_FOUND, "Note not found: ideas/ghost.md")
    assert result == "ERROR [NOT_FOUND]: Note not found: ideas/ghost.md"


def test_error_codes_are_strings() -> None:
    assert isinstance(NOT_FOUND, str)
    assert isinstance(ALREADY_EXISTS, str)
    assert isinstance(OUTSIDE_VAULT, str)
    assert isinstance(SECTION_NOT_FOUND, str)


def test_error_contains_code_and_message() -> None:
    result = error(ALREADY_EXISTS, "some message")
    assert f"[{ALREADY_EXISTS.value}]" in result
    assert "some message" in result
