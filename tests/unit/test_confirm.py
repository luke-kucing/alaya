"""Unit tests for server-side two-phase confirmation."""
import time
from pathlib import Path

import pytest

from alaya import confirm
from alaya.confirm import (
    ConfirmError,
    ConfirmMode,
    audit_id_for,
    format_proposal,
    get_mode,
    get_ttl,
    guard,
    issue_token,
    token_id,
    verify_token,
)


@pytest.fixture(autouse=True)
def _default_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALAYA_CONFIRM_MODE", raising=False)
    monkeypatch.delenv("ALAYA_CONFIRM_TTL", raising=False)


class TestMode:
    def test_defaults_to_required(self) -> None:
        assert get_mode() is ConfirmMode.REQUIRED

    @pytest.mark.parametrize("value,expected", [
        ("off", ConfirmMode.OFF),
        ("optional", ConfirmMode.OPTIONAL),
        ("REQUIRED", ConfirmMode.REQUIRED),
        ("  off  ", ConfirmMode.OFF),
    ])
    def test_parses_env_var(self, monkeypatch: pytest.MonkeyPatch, value, expected) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", value)
        assert get_mode() is expected

    def test_unknown_value_falls_back_to_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "yolo")
        assert get_mode() is ConfirmMode.REQUIRED

    def test_ttl_defaults_and_parses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert get_ttl() == 60
        monkeypatch.setenv("ALAYA_CONFIRM_TTL", "5")
        assert get_ttl() == 5

    @pytest.mark.parametrize("bad", ["nope", "0", "-3"])
    def test_bad_ttl_falls_back(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_TTL", bad)
        assert get_ttl() == 60


class TestTokens:
    def test_round_trip(self) -> None:
        args = {"path": "ideas/a.md"}
        verify_token("delete_note_tool", args, issue_token("delete_note_tool", args))

    def test_rejects_different_args(self) -> None:
        token = issue_token("delete_note_tool", {"path": "ideas/a.md"})
        with pytest.raises(ConfirmError, match="does not match"):
            verify_token("delete_note_tool", {"path": "ideas/b.md"}, token)

    def test_rejects_different_tool(self) -> None:
        args = {"path": "ideas/a.md"}
        token = issue_token("delete_note_tool", args)
        with pytest.raises(ConfirmError, match="does not match"):
            verify_token("move_note_tool", args, token)

    def test_rejects_expired_token(self) -> None:
        args = {"path": "ideas/a.md"}
        token = issue_token("delete_note_tool", args, ttl=-1)
        with pytest.raises(ConfirmError, match="expired"):
            verify_token("delete_note_tool", args, token)

    @pytest.mark.parametrize("bad", ["", "garbage", "notanumber.abc", "123"])
    def test_rejects_malformed_token(self, bad: str) -> None:
        with pytest.raises(ConfirmError):
            verify_token("delete_note_tool", {}, bad)

    def test_tampered_signature_rejected(self) -> None:
        args = {"path": "ideas/a.md"}
        expiry, _, sig = issue_token("delete_note_tool", args).partition(".")
        tampered = f"{expiry}.{'0' * len(sig)}"
        with pytest.raises(ConfirmError):
            verify_token("delete_note_tool", args, tampered)

    def test_arg_order_does_not_matter(self) -> None:
        token = issue_token("t", {"a": 1, "b": 2})
        verify_token("t", {"b": 2, "a": 1}, token)


class TestGuard:
    def test_required_mode_returns_a_proposal_first(self) -> None:
        out = guard("delete_note_tool", {"path": "a"}, "", lambda: "would archive a")
        assert out is not None
        assert "CONFIRM REQUIRED" in out
        assert "would archive a" in out
        assert "confirm_token=" in out

    def test_valid_token_lets_the_call_through(self) -> None:
        args = {"path": "a"}
        token = issue_token("delete_note_tool", args)
        assert guard("delete_note_tool", args, token, lambda: "unused") is None

    def test_off_mode_never_gates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "off")
        assert guard("delete_note_tool", {"path": "a"}, "", lambda: "unused") is None

    def test_optional_mode_allows_unconfirmed_calls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "optional")
        assert guard("delete_note_tool", {"path": "a"}, "", lambda: "unused") is None

    def test_optional_mode_still_validates_a_supplied_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "optional")
        with pytest.raises(ConfirmError):
            guard("delete_note_tool", {"path": "a"}, "bogus.token", lambda: "unused")

    def test_preview_is_not_built_when_not_needed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "off")
        calls = []
        guard("delete_note_tool", {"path": "a"}, "", lambda: calls.append(1) or "x")
        assert calls == []


class TestAuditPairing:
    def test_propose_and_execute_share_an_id(self) -> None:
        args = {"path": "a"}
        proposal = format_proposal("delete_note_tool", args, "preview")
        propose_id = audit_id_for(args, proposal)

        token = proposal.split('confirm_token="')[1].split('"')[0]
        execute_id = audit_id_for({**args, "confirm_token": token}, "Archived.")

        assert propose_id is not None
        assert propose_id == execute_id

    def test_none_for_unrelated_calls(self) -> None:
        assert audit_id_for({"path": "a"}, "Archived.") is None

    def test_token_id_is_stable(self) -> None:
        token = issue_token("t", {})
        assert token_id(token) == token_id(token)
        assert len(token_id(token)) == 12
