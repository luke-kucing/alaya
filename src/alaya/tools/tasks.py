"""Task tools: get_todos, complete_todo."""
import logging
import re
from pathlib import Path

from fastmcp import FastMCP
from alaya.errors import error, NOT_FOUND, OUTSIDE_VAULT
from alaya.vault import resolve_note_path
from alaya.tools._locks import get_path_lock, atomic_write

logger = logging.getLogger(__name__)

_TODO_PATTERN = re.compile(r"^- \[ \] (.+)$")


def get_todos(
    vault: Path,
    directories: list[str] | None = None,
) -> list[dict]:
    """Scan vault for open tasks (- [ ] ...). Returns list of {path, line, text}."""
    results = []

    if directories:
        # Validate directories stay within vault root
        search_roots = []
        vault_resolved = vault.resolve()
        for d in directories:
            # nosemgrep: semgrep.alaya-path-traversal — validated by relative_to() on next line
            root = (vault / d).resolve()
            try:
                root.relative_to(vault_resolved)
            except ValueError:
                raise ValueError(f"Directory '{d}' escapes vault root")
            search_roots.append(root)
    else:
        search_roots = [vault]

    for root in search_roots:
        for md_file in root.rglob("*.md"):
            # skip the .zk directory
            if ".zk" in md_file.parts:
                continue
            try:
                rel = str(md_file.relative_to(vault))
                for line_num, line in enumerate(md_file.read_text().splitlines(), start=1):
                    m = _TODO_PATTERN.match(line.strip())
                    if m:
                        results.append({
                            "path": rel,
                            "line": line_num,
                            "text": m.group(1),
                        })
            except OSError as e:
                logger.warning("Skipping %s during todo scan: %s", md_file, e)

    return results


def complete_todo(
    path: str,
    line: int,
    task_text: str,
    vault: Path,
) -> None:
    """Mark a task complete. Uses fuzzy ±5 line fallback if line number is stale."""
    note_path = resolve_note_path(path, vault)

    with get_path_lock(note_path):
        lines = note_path.read_text().splitlines(keepends=True)

        # try exact line first (1-indexed)
        exact_idx = line - 1
        if 0 <= exact_idx < len(lines):
            if _TODO_PATTERN.match(lines[exact_idx].strip()) and task_text in lines[exact_idx]:
                lines[exact_idx] = lines[exact_idx].replace("- [ ]", "- [x]", 1)
                atomic_write(note_path, "".join(lines))
                return

        # fuzzy fallback: search ±5 lines around the given line
        search_start = max(0, exact_idx - 5)
        search_end = min(len(lines), exact_idx + 6)
        for i in range(search_start, search_end):
            if _TODO_PATTERN.match(lines[i].strip()) and task_text in lines[i]:
                lines[i] = lines[i].replace("- [ ]", "- [x]", 1)
                atomic_write(note_path, "".join(lines))
                return

    raise ValueError(f"Task not found: '{task_text}' near line {line} in {path}")


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def get_todos_tool(directories: list[str] | None = None) -> str:
        """Find all open tasks (- [ ] ...) in the vault. Optionally restrict to directories."""
        todos = get_todos(vault, directories=directories or None)
        if not todos:
            return "No open tasks found."
        lines = [f"- `{t['path']}:{t['line']}` — {t['text']}" for t in todos]
        return "\n".join(lines)

    @mcp.tool()
    def complete_todo_tool(path: str, line: int, task_text: str) -> str:
        """Mark a task as complete. Uses fuzzy fallback if line number is stale."""
        try:
            complete_todo(path, line, task_text, vault)
            return f"Completed: '{task_text}'"
        except FileNotFoundError as e:
            return error(NOT_FOUND, str(e))
        except ValueError as e:
            return error(OUTSIDE_VAULT, str(e))

