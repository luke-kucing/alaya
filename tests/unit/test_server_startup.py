"""Tests for server startup checks."""
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from alaya import server
from alaya.server import _maybe_start_reembed
from alaya.backend.zk import ZkBackend
from alaya.backend.protocol import VaultConfig, LinkResolution


def test_zk_backend_check_available_succeeds():
    config = VaultConfig(
        root=Path("/tmp/test"),
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    backend = ZkBackend(config)
    mock_result = subprocess.CompletedProcess(args=["zk", "--version"], returncode=0, stdout="zk 0.14.0\n", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        backend.check_available()  # should not raise


def test_zk_backend_check_available_raises_when_not_installed():
    config = VaultConfig(
        root=Path("/tmp/test"),
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    backend = ZkBackend(config)
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="zk CLI not found"):
            backend.check_available()


def test_maybe_start_reembed_no_op_when_models_match(tmp_path: Path) -> None:
    store = MagicMock()
    with patch("alaya.index.store.get_index_model", return_value="model-a"), \
         patch("alaya.index.models.get_active_model") as mock_active:
        mock_active.return_value.key = "model-a"
        threads_before = threading.active_count()
        _maybe_start_reembed(tmp_path, store)
        assert threading.active_count() == threads_before


def test_maybe_start_reembed_no_op_when_index_empty(tmp_path: Path) -> None:
    store = MagicMock()
    with patch("alaya.index.store.get_index_model", return_value=None), \
         patch("alaya.index.models.get_active_model") as mock_active:
        mock_active.return_value.key = "model-a"
        threads_before = threading.active_count()
        _maybe_start_reembed(tmp_path, store)
        assert threading.active_count() == threads_before


def test_maybe_start_reembed_spawns_thread_on_mismatch(tmp_path: Path) -> None:
    store = MagicMock()
    started = []

    def fake_reembed(*args, **kwargs):
        started.append(True)

    with patch("alaya.index.store.get_index_model", return_value="old-model"), \
         patch("alaya.index.models.get_active_model") as mock_active, \
         patch("alaya.index.reindex.reembed_background", side_effect=fake_reembed):
        mock_active.return_value.key = "new-model"
        _maybe_start_reembed(tmp_path, store)
        import time; time.sleep(0.05)

    assert started


class TestParseArgs:
    def test_profile_defaults_to_none(self) -> None:
        from alaya.server import _parse_args

        assert _parse_args([]).profile is None

    def test_profile_flag_is_parsed(self) -> None:
        from alaya.server import _parse_args

        assert _parse_args(["--profile", "orchestrator"]).profile == "orchestrator"

    def test_unknown_flag_exits(self) -> None:
        from alaya.server import _parse_args

        with pytest.raises(SystemExit):
            _parse_args(["--nope"])


class TestResponseShaping:
    """The instrumentation wrapper must cap and annotate every tool response."""

    def _wrap(self, vault: Path, fn, name: str, kwargs: dict):
        """Run fn through the same shaping the server wrapper applies."""
        from alaya.responses import shape
        from alaya.server import _TRUNCATION_HINTS

        return shape(
            fn(**kwargs),
            unbounded=bool(kwargs.get("unbounded")),
            hint=_TRUNCATION_HINTS.get(name),
        )

    def test_every_response_carries_a_token_count(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        out = self._wrap(
            vault,
            lambda **_: get_note("projects/second-brain.md", vault),
            "get_note",
            {},
        )
        assert "<!-- token_count:" in out

    def test_cap_applies_with_a_tool_specific_hint(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "100")
        out = self._wrap(
            vault, lambda **_: "word " * 2000, "search_notes", {}
        )
        assert "truncated" in out
        assert "narrow the query" in out

    def test_unbounded_kwarg_bypasses_the_cap(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "100")
        out = self._wrap(
            vault, lambda **_: "word " * 2000, "search_notes", {"unbounded": True}
        )
        assert "truncated" not in out

    def test_memory_recall_token_count_is_not_duplicated(self, vault: Path) -> None:
        from alaya.responses import shape

        body = "recall body\n\n<!-- token_count: 5; sources: 2 -->"
        assert shape(body).count("token_count:") == 1

    def test_every_tool_name_in_the_hint_map_exists(self, vault: Path) -> None:
        import asyncio

        from fastmcp import FastMCP
        from alaya.server import _TRUNCATION_HINTS
        from alaya.tools import graph, inbox, read, search, structure, tasks

        mcp = FastMCP(name="alaya-test")
        for mod in (read, search, structure, tasks, inbox, graph):
            mod._register(mcp, vault)
        registered = {t.name for t in asyncio.run(mcp.list_tools())}

        assert set(_TRUNCATION_HINTS) <= registered

    def test_every_hinted_tool_declares_unbounded(self, vault: Path) -> None:
        import asyncio

        from fastmcp import FastMCP
        from alaya.server import _TRUNCATION_HINTS
        from alaya.tools import graph, inbox, read, search, structure, tasks

        mcp = FastMCP(name="alaya-test")
        for mod in (read, search, structure, tasks, inbox, graph):
            mod._register(mcp, vault)
        by_name = {t.name: t for t in asyncio.run(mcp.list_tools())}

        for name in _TRUNCATION_HINTS:
            params = by_name[name].parameters["properties"]
            assert "unbounded" in params, f"{name} is hinted but cannot be unbounded"


# --- Streamable HTTP transport (#157) ---



_INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {},
               "clientInfo": {"name": "t", "version": "0"}},
}
_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


class TestHttpTransport:
    def test_parses_host_port(self) -> None:
        assert server._parse_args(["--http", "127.0.0.1:7400"]).http == ("127.0.0.1", 7400)
        assert server._parse_args(["--http", "[::1]:7400"]).http == ("::1", 7400)
        assert server._parse_args([]).http is None

    @pytest.mark.parametrize("bad", ["7400", "host:", "host:99999", ":7400"])
    def test_rejects_bad_address(self, bad: str) -> None:
        with pytest.raises(SystemExit):
            server._parse_args(["--http", bad])

    def test_token_required_when_set(self, monkeypatch) -> None:
        from starlette.testclient import TestClient

        monkeypatch.setenv("ALAYA_HTTP_TOKEN", "s3cret")
        monkeypatch.setattr(server.mcp, "auth", None)
        server._configure_http_auth("0.0.0.0")
        with TestClient(server.mcp.http_app()) as c:
            assert c.post("/mcp", json=_INIT, headers=_HEADERS).status_code == 401
            bad = {**_HEADERS, "Authorization": "Bearer wrong"}
            assert c.post("/mcp", json=_INIT, headers=bad).status_code == 401
            ok = {**_HEADERS, "Authorization": "Bearer s3cret"}
            assert c.post("/mcp", json=_INIT, headers=ok).status_code == 200

    def test_warns_on_open_lan_bind(self, monkeypatch, caplog) -> None:
        monkeypatch.delenv("ALAYA_HTTP_TOKEN", raising=False)
        monkeypatch.setattr(server.mcp, "auth", None)
        server._configure_http_auth("127.0.0.1")
        assert "ALAYA_HTTP_TOKEN" not in caplog.text
        server._configure_http_auth("0.0.0.0")
        assert "ALAYA_HTTP_TOKEN" in caplog.text
        assert server.mcp.auth is None
