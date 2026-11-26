"""Tests that every tool is registered under its bare, README-documented name (#150)."""
import re
from pathlib import Path

import pytest
from fastmcp import FastMCP

from alaya.tools import (
    capture, edit, enrich, external, graph, inbox, ingest,
    memory, read, search, stats, structure, tasks, write,
)

EXPECTED = {
    # read & navigate
    "get_note", "list_notes", "get_backlinks", "get_links", "get_tags",
    "find_references", "vault_graph", "vault_stats",
    # write & capture
    "create_note", "append_to_note", "update_tags", "smart_capture",
    "capture_to_inbox", "get_inbox", "clear_inbox_item",
    # search & enrichment
    "search_notes", "enrich_chunk_context", "store_propositions", "store_summary",
    # agent memory
    "memory_recall", "memory_checkpoint", "memory_resume", "memory_supersede", "memory_stale",
    # tasks
    "get_todos", "append_todo", "complete_todo",
    "create_task", "ready_tasks", "claim_task", "renew_task", "release_task",
    # edit & structure
    "move_note", "rename_note", "delete_note", "replace_section", "extract_section",
    # ingest & external
    "ingest", "batch_ingest", "reindex_vault", "pull_external", "push_external",
}


@pytest.mark.asyncio
async def test_all_expected_tools_registered(vault: Path) -> None:
    mcp = FastMCP(name="alaya-test")
    for mod in (read, search, structure, edit, graph, capture, external,
                write, inbox, tasks, ingest, stats, enrich, memory):
        mod._register(mcp, vault)

    registered = {t.name for t in await mcp.list_tools()}
    assert registered == EXPECTED


def test_every_tool_is_documented_in_readme() -> None:
    readme = (Path(__file__).parents[2] / "README.md").read_text()
    documented = set(re.findall(r"^\| `(\w+)` \|", readme, re.MULTILINE))
    # vault_health is registered by server.py, not a tool module
    assert EXPECTED | {"vault_health"} <= documented
