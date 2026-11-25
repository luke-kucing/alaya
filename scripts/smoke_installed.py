"""Smoke-test an *installed* alaya (a built wheel, not the source tree).

Run against a freshly resolved install, outside the lockfile, so dependency
drift (e.g. a new fastmcp major) is caught before a release:

    uv build
    uv run --isolated --no-project --with dist/*.whl python scripts/smoke_installed.py vault_fixture

Copies the vault, registers every tool with the production middleware, and
makes real MCP calls through an in-process client.
"""
import asyncio
import shutil
import sys
import tempfile
from pathlib import Path


async def _calls(mcp) -> None:
    from fastmcp import Client

    async with Client(mcp) as client:
        names = {t.name for t in await client.list_tools()}
        assert {"get_note", "search_notes", "memory_recall"} <= names, sorted(names)

        note = await client.call_tool("get_note", {"path": "projects/second-brain.md"})
        assert "<!-- token_count:" in note.content[0].text, note.content[0].text[:200]

        missing = await client.call_tool("get_note", {"path": "nope.md"}, raise_on_error=False)
        assert "NOT_FOUND" in missing.content[0].text


def main(fixture: str) -> None:
    import alaya
    import alaya.server as server

    assert "site-packages" in alaya.__file__, f"testing the source tree, not the install: {alaya.__file__}"
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        shutil.copytree(fixture, vault)
        server._register_all(vault)
        server._instrument_tools(vault)
        asyncio.run(_calls(server.mcp))
    print("installed alaya OK")


if __name__ == "__main__":
    main(sys.argv[1])
