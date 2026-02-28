"""Inbox tools: capture_to_inbox, get_inbox, clear_inbox_item."""
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND

_INBOX_FILENAME = "inbox.md"


def _inbox_path(vault: Path) -> Path:
    return vault / _INBOX_FILENAME


def capture_to_inbox(text: str, vault: Path) -> str:
    """Append a timestamped entry to inbox.md and return a confirmation string."""
    inbox = _inbox_path(vault)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- {timestamp} {text}"

    existing = inbox.read_text() if inbox.exists() else "# Inbox\n\nQuick capture. Process weekly.\n"
    separator = "\n" if existing.endswith("\n") else "\n"
    inbox.write_text(existing + separator + entry + "\n")

    return f"Captured: {entry}"


def get_inbox(vault: Path) -> str:
    """Return the contents of inbox.md."""
    inbox = _inbox_path(vault)
    if not inbox.exists():
        return "Inbox is empty."

    content = inbox.read_text().strip()

    # collect bullet items
    items = [l for l in content.splitlines() if l.strip().startswith("- ")]
    if not items:
        return "Inbox is empty. No items to process."

    return content


def clear_inbox_item(text: str, vault: Path) -> None:
    """Remove the first inbox line whose item content matches `text`.

    Matching strips the timestamp prefix (e.g. '2026-02-23 09:15 ') before
    comparing, so Claude can pass the captured text without the timestamp.
    Falls back to substring match if no exact content match is found, to
    handle cases where only part of the text is provided.

    Raises ValueError if no matching line is found.
    """
    import re
    inbox = _inbox_path(vault)
    lines = inbox.read_text().splitlines(keepends=True)

    _TS_PREFIX = re.compile(r"^-\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+")

    # first pass: exact content match (strip timestamp prefix)
    for i, line in enumerate(lines):
        stripped = _TS_PREFIX.sub("", line.rstrip())
        if stripped == text:
            lines.pop(i)
            inbox.write_text("".join(lines))
            return

    # second pass: substring match fallback
    for i, line in enumerate(lines):
        if text in line:
            lines.pop(i)
            inbox.write_text("".join(lines))
            return

    raise ValueError(f"Inbox item not found: '{text}'")


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def capture_to_inbox_tool(text: str) -> str:
        """Capture a quick note to inbox.md with a timestamp."""
        return capture_to_inbox(text, vault)

    @mcp.tool()
    def get_inbox_tool() -> str:
        """Return the current inbox contents."""
        return get_inbox(vault)

    @mcp.tool()
    def clear_inbox_item_tool(text: str) -> str:
        """Remove an inbox item by matching text."""
        try:
            clear_inbox_item(text, vault)
            return f"Removed inbox item: '{text}'"
        except ValueError as e:
            return error(NOT_FOUND, str(e))

