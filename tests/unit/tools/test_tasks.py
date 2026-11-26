"""Unit tests for task tools: checkbox todos and the task ledger."""
import multiprocessing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from alaya.tools.tasks import (
    TaskConflict,
    _read_task,
    append_todo,
    clean_todo,
    _write_task,
    claim_task,
    complete_todo,
    create_task,
    get_todos,
    ready_tasks,
    release_task,
    renew_task,
)


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


# --- Task ledger (#170) ---

def _try_claim(vault: str, owner: str) -> bool:
    """Run in a child process; module-level so spawn can pickle it."""
    try:
        claim_task("race", owner, Path(vault))
        return True
    except TaskConflict:
        return False


def _race(vault: Path, n: int = 8) -> list[bool]:
    with multiprocessing.get_context("spawn").Pool(n) as pool:
        return pool.starmap(_try_claim, [(str(vault), f"agent-{i}") for i in range(n)])


class TestTaskLedger:
    def test_create_writes_plain_markdown_task(self, vault: Path) -> None:
        t = create_task("Fix the parser", vault, body="It breaks on tabs.", blocked_by=["[[other]]"])
        text = (vault / t["path"]).read_text()
        assert t["path"] == "tasks/fix-the-parser.md"
        assert "type: task" in text and "status: open" in text
        assert "- '[[other]]'" in text  # a quoted wikilink, not a nested YAML list
        assert "# Fix the parser" in text and "It breaks on tabs." in text

    def test_create_refuses_existing(self, vault: Path) -> None:
        create_task("Same", vault)
        with pytest.raises(FileExistsError):
            create_task("Same", vault)

    def test_rejects_path_like_task(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            claim_task("../notes/secret", "a", vault)
        with pytest.raises(ValueError):
            claim_task("x", "bad\nowner", vault)

    def test_live_lease_blocks_others_and_names_owner(self, vault: Path) -> None:
        create_task("One", vault)
        claim_task("one", "alice", vault)
        with pytest.raises(TaskConflict, match="alice"):
            claim_task("one", "bob", vault)

    def test_expired_lease_is_claimable(self, vault: Path) -> None:
        create_task("One", vault)
        claim_task("one", "alice", vault)
        _expire(vault / "tasks/one.md")
        assert claim_task("[[one]]", "bob", vault)["owner"] == "bob"

    def test_ready_excludes_unfinished_blockers(self, vault: Path) -> None:
        create_task("Base", vault)
        create_task("Next", vault, blocked_by=["base"])
        create_task("Orphan", vault, blocked_by=["missing"])
        assert [t["task"] for t in ready_tasks(vault)] == ["base"]
        with pytest.raises(TaskConflict):
            claim_task("next", "alice", vault)
        claim_task("base", "alice", vault)
        release_task("base", "alice", vault, status="done")
        assert [t["task"] for t in ready_tasks(vault)] == ["next"]

    def test_ready_includes_expired_claims(self, vault: Path) -> None:
        create_task("One", vault)
        claim_task("one", "alice", vault)
        assert ready_tasks(vault) == []
        _expire(vault / "tasks/one.md")
        assert [t["task"] for t in ready_tasks(vault)] == ["one"]

    def test_release_by_non_owner_rejected(self, vault: Path) -> None:
        create_task("One", vault)
        claim_task("one", "alice", vault)
        with pytest.raises(TaskConflict):
            release_task("one", "bob", vault)
        with pytest.raises(TaskConflict):
            renew_task("one", "bob", vault)

    def test_release_logs_history(self, vault: Path) -> None:
        create_task("One", vault)
        claim_task("one", "alice", vault)
        release_task("one", "alice", vault, status="blocked", note="needs\nthe API key")
        with pytest.raises(TaskConflict):
            claim_task("one", "bob", vault)
        text = (vault / "tasks/one.md").read_text()
        assert "## Log" in text and "alice → blocked: needs the API key" in text
        meta, _ = _read_task(vault / "tasks/one.md")
        assert meta["status"] == "blocked" and meta["owner"] == ""

    def test_renew_extends_lease(self, vault: Path) -> None:
        create_task("One", vault)
        first = claim_task("one", "alice", vault, lease_minutes=1)
        assert renew_task("one", "alice", vault, lease_minutes=120)["lease_until"] > first["lease_until"]

    def test_processes_racing_one_claim_one_wins(self, vault: Path) -> None:
        create_task("Race", vault)
        assert sum(_race(vault)) == 1

    def test_processes_racing_an_expired_lease_one_wins(self, vault: Path) -> None:
        create_task("Race", vault)
        claim_task("race", "old", vault)
        _expire(vault / "tasks/race.md")
        assert sum(_race(vault)) == 1
        assert _read_task(vault / "tasks/race.md")[0]["owner"] != "old"


def _expire(path: Path) -> None:
    meta, body = _read_task(path)
    meta["lease_until"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    _write_task(path, meta, body)


class TestAppendTodo:
    """#148: safe '- [ ]' appends under a section."""

    def _note(self, vault: Path, body: str) -> str:
        (vault / "projects" / "todo-test.md").write_text(body)
        return "projects/todo-test.md"

    def test_appends_to_end_of_existing_list(self, vault: Path) -> None:
        rel = self._note(vault, "# P\n\n## Tasks\n\n- [ ] one\n- [x] two\n\n## Notes\n\nkeep me\n")
        assert append_todo(rel, "three", vault) == "- [ ] three"
        assert (vault / rel).read_text() == (
            "# P\n\n## Tasks\n\n- [ ] one\n- [x] two\n- [ ] three\n\n## Notes\n\nkeep me\n"
        )

    def test_creates_missing_section_at_end(self, vault: Path) -> None:
        rel = self._note(vault, "# P\n\nbody")
        append_todo(rel, "first", vault, section="Next")
        assert (vault / rel).read_text() == "# P\n\nbody\n\n## Next\n\n- [ ] first\n"

    def test_section_match_is_case_insensitive(self, vault: Path) -> None:
        rel = self._note(vault, "## tasks\n- [ ] a\n")
        append_todo(rel, "b", vault)
        assert (vault / rel).read_text() == "## tasks\n- [ ] a\n- [ ] b\n"

    @pytest.mark.parametrize("raw", ["- [ ] x", "[ ] x", "- [x] x", "* x", "  x  "])
    def test_strips_accidental_prefixes(self, raw: str) -> None:
        assert clean_todo(raw) == "x"

    @pytest.mark.parametrize("bad", ["", "   ", "- [ ] ", "a\nb"])
    def test_rejects_empty_or_multiline(self, vault: Path, bad: str) -> None:
        rel = self._note(vault, "x\n")
        with pytest.raises(ValueError):
            append_todo(rel, bad, vault)
        assert (vault / rel).read_text() == "x\n"

    def test_rejects_path_outside_vault(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            append_todo("../escape.md", "x", vault)

    def test_missing_note(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            append_todo("projects/nope.md", "x", vault)

    def test_new_task_is_listed_by_get_todos(self, vault: Path) -> None:
        rel = self._note(vault, "## Tasks\n")
        append_todo(rel, "findable", vault)
        assert any(t["path"] == rel and t["text"] == "findable" for t in get_todos(vault, directories=["projects"]))
