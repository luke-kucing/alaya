"""Tests that all expected tools are registered on the FastMCP server."""
import pytest
from alaya.server import mcp


@pytest.mark.asyncio
async def test_all_expected_tools_registered() -> None:
    registered = {t.name for t in await mcp.list_tools()}
    expected = {
        "get_note_tool",
        "list_notes_tool",
        "get_backlinks_tool",
        "get_links_tool",
        "get_tags_tool",
        "reindex_vault_tool",
        "create_note_tool",
        "append_to_note_tool",
        "update_tags_tool",
        "capture_to_inbox_tool",
        "get_inbox_tool",
        "clear_inbox_item_tool",
        "search_notes_tool",
        "move_note_tool",
        "rename_note_tool",
        "delete_note_tool",
        "find_references_tool",
        "replace_section_tool",
        "extract_section_tool",
        "get_todos_tool",
        "complete_todo_tool",
        "ingest_tool",
    }
    missing = expected - registered
    assert not missing, f"Tools not registered: {missing}"
