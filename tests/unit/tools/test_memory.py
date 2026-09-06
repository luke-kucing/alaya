"""Unit tests for agent memory tools."""
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import FastMCP

from alaya import tokens
from alaya.backend.config import get_backend
from alaya.tools import memory
from alaya.tools.memory import (
    memory_checkpoint,
    memory_recall,
    memory_resume,
    _safe_session_id,
)


@pytest.fixture
def backend(vault: Path):
    return get_backend(vault)


class TestSessionIdValidation:
    @pytest.mark.parametrize("bad", ["", "  ", ".", "..", "a/b", "a\\b", ".hidden"])
    def test_rejects_traversal_and_empty(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _safe_session_id(bad)

    def test_accepts_plain_id(self) -> None:
        assert _safe_session_id(" run-42 ") == "run-42"

    def test_checkpoint_rejects_escaping_session_id(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            memory_checkpoint("../escape", "planner", "summary", vault)


class TestCheckpoint:
    def test_writes_to_agent_dir_with_agent_memory_type(self, vault: Path, backend) -> None:
        path = memory_checkpoint(
            "run-1", "planner", "Did the thing.", vault, backend=backend,
        )
        assert path == "agents/run-1/checkpoint.md"
        content = (vault / path).read_text()
        assert "type: agent-memory" in content
        assert "session: run-1" in content
        assert "Did the thing." in content

    def test_entities_become_wikilinks(self, vault: Path, backend) -> None:
        path = memory_checkpoint(
            "run-2", "planner", "s", vault,
            entities=["Alice", "Project Alaya"], backend=backend,
        )
        content = (vault / path).read_text()
        assert "[[Alice]]" in content
        assert "[[Project Alaya]]" in content

    def test_open_items_and_decisions_rendered(self, vault: Path, backend) -> None:
        path = memory_checkpoint(
            "run-3", "gen", "s", vault,
            open_items=["fix the gate"], decisions=["use RRF"], backend=backend,
        )
        content = (vault / path).read_text()
        assert "- [ ] fix the gate" in content
        assert "- use RRF" in content

    def test_overwrites_previous_checkpoint(self, vault: Path, backend) -> None:
        memory_checkpoint("run-4", "a", "first", vault, backend=backend)
        path = memory_checkpoint("run-4", "a", "second", vault, backend=backend)
        content = (vault / path).read_text()
        assert "second" in content
        assert "first" not in content

    def test_emits_note_event(self, vault: Path, backend) -> None:
        from alaya.events import NoteEvent, EventType, on_note_change, clear_listeners

        seen: list[NoteEvent] = []
        clear_listeners()
        on_note_change(seen.append)
        try:
            memory_checkpoint("run-5", "a", "s", vault, backend=backend)
        finally:
            clear_listeners()

        assert len(seen) == 1
        assert seen[0].event_type is EventType.CREATED
        assert seen[0].path == "agents/run-5/checkpoint.md"

    def test_rejects_out_of_range_confidence(self, vault: Path, backend) -> None:
        with pytest.raises(ValueError):
            memory_checkpoint("run-6", "a", "s", vault, confidence=1.5, backend=backend)

    def test_respects_configured_agent_dir(self, vault: Path, backend) -> None:
        backend.config.agent_dir = "runs"
        path = memory_checkpoint("run-7", "a", "s", vault, backend=backend)
        assert path == "runs/run-7/checkpoint.md"


class TestResume:
    def test_round_trip_returns_summary(self, vault: Path, backend) -> None:
        memory_checkpoint(
            "run-10", "planner", "The summary line.", vault,
            open_items=["next thing"], backend=backend,
        )
        out = memory_resume("run-10", vault, backend=backend)
        assert "The summary line." in out
        assert "next thing" in out
        assert "token_count:" in out

    def test_includes_one_hop_linked_notes(self, vault: Path, backend) -> None:
        target = vault / "ideas" / "linked-target.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("---\ntitle: Linked Target\n---\n\nBody of the linked note.\n")

        memory_checkpoint(
            "run-11", "planner", "s", vault,
            entities=["Linked Target"], backend=backend,
        )
        out = memory_resume("run-11", vault, budget_tokens=4000, backend=backend)
        assert "Linked context" in out
        assert "Body of the linked note." in out

    def test_missing_checkpoint_is_not_an_error(self, vault: Path, backend) -> None:
        out = memory_resume("nope", vault, backend=backend)
        assert "No checkpoint" in out
        assert "sources: 0" in out

    def test_respects_budget(self, vault: Path, backend) -> None:
        memory_checkpoint("run-12", "planner", "word " * 2000, vault, backend=backend)
        out = memory_resume("run-12", vault, budget_tokens=200, backend=backend)
        assert tokens.count_tokens(out) <= 200

    def test_rejects_non_positive_budget(self, vault: Path, backend) -> None:
        with pytest.raises(ValueError):
            memory_resume("run-13", vault, budget_tokens=0, backend=backend)


class TestRecall:
    def test_no_index_degrades_gracefully(self, vault: Path, backend) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=False):
            out = memory_recall("anything", vault, backend=backend)
        assert "No index available" in out
        assert "sources: 0" in out

    def test_returns_chunk_text_within_budget(self, vault: Path, backend) -> None:
        fake = [
            {"path": "ideas/a.md", "title": "A", "score": 0.9, "text": "word " * 400},
            {"path": "ideas/b.md", "title": "B", "score": 0.8, "text": "other " * 400},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=fake):
            out = memory_recall("q", vault, budget_tokens=300, backend=backend)

        assert tokens.count_tokens(out) <= 300
        assert "ideas/a.md" in out
        assert "truncated" in out

    def test_empty_results_message(self, vault: Path, backend) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=[]):
            out = memory_recall("q", vault, backend=backend)
        assert "No vault context found" in out

    def test_dedupes_repeated_paths(self, vault: Path, backend) -> None:
        fake = [
            {"path": "ideas/a.md", "title": "A", "score": 0.9, "text": "first chunk"},
            {"path": "ideas/a.md", "title": "A", "score": 0.5, "text": "second chunk"},
        ]
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=fake):
            out = memory_recall("q", vault, budget_tokens=2000, backend=backend)
        assert out.count("ideas/a.md") == 1
        assert "sources: 1" in out

    def test_rejects_non_positive_budget(self, vault: Path, backend) -> None:
        with pytest.raises(ValueError):
            memory_recall("q", vault, budget_tokens=0, backend=backend)

    def test_includes_agent_memory_by_default(self, vault: Path, backend) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=[]) as mock:
            memory_recall("q", vault, backend=backend)
        assert mock.call_args.kwargs["exclude_types"] is None


class TestRegistration:
    @pytest.mark.asyncio
    async def test_tools_registered(self, vault: Path, backend) -> None:
        test_mcp = FastMCP(name="alaya-test")
        memory._register(test_mcp, vault, backend=backend)
        names = {t.name for t in await test_mcp.list_tools()}
        assert names == {
            "memory_recall_tool",
            "memory_checkpoint_tool",
            "memory_resume_tool",
        }

    @pytest.mark.asyncio
    async def test_invalid_argument_returns_error_string(self, vault: Path, backend) -> None:
        test_mcp = FastMCP(name="alaya-test")
        memory._register(test_mcp, vault, backend=backend)
        tool = {t.name: t for t in await test_mcp.list_tools()}["memory_checkpoint_tool"]
        out = tool.fn(session_id="../nope", agent="a", summary_md="s")
        assert out.startswith("ERROR [")
