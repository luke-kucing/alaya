"""Task tools: get_todos, complete_todo."""
import re
from pathlib import Path

from fastmcp import FastMCP
from alaya.config import get_vault_root
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT
from alaya.vault import resolve_note_path

_TODO_PATTERN = re.compile(r"^- \[ \] (.+)$")
_DONE_PATTERN = re.compile(r"^- \[x\] (.+)$", re.IGNORECASE)


def get_todos(
    vault: Path,
    directories: list[str] | None = None,
) -> list[dict]:
    """Scan vault for open tasks (- [ ] ...). Returns list of {path, line, text}."""
    results = []

    if directories:
        search_roots = [vault / d for d in directories]
    else:
        search_roots = [vault]

    for root in search_roots:
        for md_file in root.rglob("*.md"):
            # skip the .zk directory
            if ".zk" in md_file.parts:
                continue
            rel = str(md_file.relative_to(vault))
            for line_num, line in enumerate(md_file.read_text().splitlines(), start=1):
                m = _TODO_PATTERN.match(line.strip())
                if m:
                    results.append({
                        "path": rel,
                        "line": line_num,
                        "text": m.group(1),
                    })

    return results


def complete_todo(
    path: str,
    line: int,
    task_text: str,
    vault: Path,
) -> None:
    """Mark a task complete. Uses fuzzy ±5 line fallback if line number is stale."""
    note_path = resolve_note_path(path, vault)
    lines = note_path.read_text().splitlines(keepends=True)

    # try exact line first (1-indexed)
    exact_idx = line - 1
    if 0 <= exact_idx < len(lines):
        if _TODO_PATTERN.match(lines[exact_idx].strip()) and task_text in lines[exact_idx]:
            lines[exact_idx] = lines[exact_idx].replace("- [ ]", "- [x]", 1)
            note_path.write_text("".join(lines))
            return

    # fuzzy fallback: search ±5 lines around the given line
    search_start = max(0, exact_idx - 5)
    search_end = min(len(lines), exact_idx + 6)
    for i in range(search_start, search_end):
        if _TODO_PATTERN.match(lines[i].strip()) and task_text in lines[i]:
            lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
            note_path.write_text("".join(lines))
            return

    raise ValueError(f"Task not found: '{task_text}' near line {line} in {path}")


# --- FastMCP tool registration ---

def _register(mcp: FastMCP) -> None:
    vault_root = get_vault_root

    @mcp.tool()
    def get_todos_tool(directories: list[str] | None = None) -> str:
        """Find all open tasks (- [ ] ...) in the vault. Optionally restrict to directories."""
        todos = get_todos(vault_root(), directories=directories or None)
        if not todos:
            return "No open tasks found."
        lines = [f"- `{t['path']}:{t['line']}` — {t['text']}" for t in todos]
        return "\n".join(lines)

    @mcp.tool()
    def complete_todo_tool(path: str, line: int, task_text: str) -> str:
        """Mark a task as complete. Uses fuzzy fallback if line number is stale."""
        try:
            complete_todo(path, line, task_text, vault_root())
            return f"Completed: '{task_text}'"
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))


try:
    from alaya.server import mcp as _mcp
    _register(_mcp)
except ImportError:
    pass
