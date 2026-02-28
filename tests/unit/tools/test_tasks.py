"""Unit tests for task tools: get_todos, complete_todo."""
from pathlib import Path

import pytest

from alaya.tools.tasks import get_todos, complete_todo


class TestGetTodos:
    def test_finds_open_tasks(self, vault: Path) -> None:
        results = get_todos(vault)
        # second-brain.md has open tasks
        tasks = [t["text"] for t in results]
        assert any("scaffold project structure" in t for t in tasks)

    def test_excludes_completed_tasks(self, vault: Path) -> None:
        results = get_todos(vault)
        tasks = [t["text"] for t in results]
        # second-brain.md has completed tasks like "write requirements doc"
        assert not any("write requirements doc" in t for t in tasks)

    def test_returns_path_and_line(self, vault: Path) -> None:
        results = get_todos(vault)
        assert results
        for t in results:
            assert "path" in t
            assert "line" in t
            assert "text" in t

    def test_filter_by_directory(self, vault: Path) -> None:
        results = get_todos(vault, directories=["projects"])
        for t in results:
            assert t["path"].startswith("projects/")

    def test_no_todos_returns_empty_list(self, vault: Path) -> None:
        # overwrite a note with no open tasks
        (vault / "projects/platform-migration.md").write_text(
            "---\ntitle: platform-migration\ndate: 2026-02-01\n---\n#project\n\nNo tasks here.\n"
        )
        results = get_todos(vault, directories=["projects"])
        paths = [t["path"] for t in results]
        assert not any("platform-migration" in p for p in paths)

    def test_also_finds_tasks_in_daily_notes(self, vault: Path) -> None:
        # plant a task in a daily note
        daily = vault / "daily/2026-02-25.md"
        daily.write_text(daily.read_text() + "\n- [ ] follow up on PR review\n")
        results = get_todos(vault)
        tasks = [t["text"] for t in results]
        assert any("follow up on PR review" in t for t in tasks)


class TestCompleteTodo:
    def test_marks_task_complete(self, vault: Path) -> None:
        # get line number from get_todos
        todos = get_todos(vault, directories=["projects"])
        scaffold_task = next(t for t in todos if "scaffold project structure" in t["text"])

        complete_todo(
            path=scaffold_task["path"],
            line=scaffold_task["line"],
            task_text=scaffold_task["text"],
            vault=vault,
        )

        content = (vault / scaffold_task["path"]).read_text()
        assert "- [x] scaffold project structure" in content

    def test_open_marker_removed(self, vault: Path) -> None:
        todos = get_todos(vault, directories=["projects"])
        scaffold_task = next(t for t in todos if "scaffold project structure" in t["text"])

        complete_todo(
            path=scaffold_task["path"],
            line=scaffold_task["line"],
            task_text=scaffold_task["text"],
            vault=vault,
        )

        content = (vault / scaffold_task["path"]).read_text()
        assert "- [ ] scaffold project structure" not in content

    def test_fuzzy_line_fallback(self, vault: Path) -> None:
        # pass a stale line number (off by 3) — should still find it via task_text
        todos = get_todos(vault, directories=["projects"])
        scaffold_task = next(t for t in todos if "scaffold project structure" in t["text"])

        complete_todo(
            path=scaffold_task["path"],
            line=scaffold_task["line"] + 3,  # stale
            task_text=scaffold_task["text"],
            vault=vault,
        )

        content = (vault / scaffold_task["path"]).read_text()
        assert "- [x] scaffold project structure" in content

    def test_task_not_found_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            complete_todo(
                path="projects/second-brain.md",
                line=1,
                task_text="this task does not exist anywhere",
                vault=vault,
            )

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            complete_todo(
                path="../../etc/passwd",
                line=1,
                task_text="anything",
                vault=vault,
            )
