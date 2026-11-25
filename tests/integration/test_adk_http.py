"""Google ADK McpToolset against `alaya --http` with a bearer token (#191).

Opt-in: skipped unless google-adk is importable. google-adk is not a project
dependency; run with:

    uv run --with google-adk pytest tests/integration/test_adk_http.py

Uses an Obsidian vault in a temp dir, so no zk binary is needed. No LLM involved.
"""
import asyncio
import os
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("google.adk.tools.mcp_tool.mcp_toolset")
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams  # noqa: E402

pytestmark = pytest.mark.integration

TOKEN = "test-token-191"


@pytest.fixture(scope="module")
def server_url(tmp_path_factory):
    vault = tmp_path_factory.mktemp("vault")
    (vault / ".obsidian").mkdir()
    (vault / "hello.md").write_text("---\ntitle: Hello\n---\nadk-marker body\n")
    (vault / "other.md").write_text("# Other\nsecond note\n")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "ALAYA_VAULT_DIR": str(vault), "ALAYA_HTTP_TOKEN": TOKEN}
    proc = subprocess.Popen(
        [sys.executable, "-m", "alaya.server", "--http", f"127.0.0.1:{port}"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 240  # cold start (index + model init) can take minutes
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.fail("alaya server exited during startup")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.3)
        else:
            pytest.fail("alaya server did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.kill()
        proc.wait()


def _toolset(url: str, token: str) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=url, headers={"Authorization": f"Bearer {token}"}
        )
    )


def test_list_and_call_tools(server_url):
    async def run():
        ts = _toolset(server_url, TOKEN)
        try:
            tools = {t.name: t for t in await ts.get_tools()}
            assert {"get_note", "list_notes"} <= tools.keys()
            result = await tools["get_note"].run_async(
                args={"path": "hello.md"}, tool_context=None
            )
            return str(result)
        finally:
            await ts.close()

    assert "adk-marker" in asyncio.run(run())


def test_wrong_token_fails(server_url):
    async def run():
        ts = _toolset(server_url, "wrong")
        try:
            await ts.get_tools()
        finally:
            await ts.close()

    with pytest.raises(Exception):
        asyncio.run(run())
