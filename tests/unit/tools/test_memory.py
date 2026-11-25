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
    memory_supersede,
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


def _memory_note(vault: Path, rel: str, *, updated: str, ttl_days: int, confidence: float) -> None:
    path = vault / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ntype: agent-memory\nconfidence: {confidence}\nttl_days: {ttl_days}\n"
        f"updated: {updated}\n---\n\nbody\n"
    )


def _recall(vault: Path, backend, fake: list[dict], **kw) -> str:
    with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
         patch("alaya.tools.search._run_corrective_search", return_value=fake):
        return memory_recall("q", vault, budget_tokens=2000, backend=backend, **kw)


class TestMemoryRecallFreshness:
    """#169: recall honors ttl_days, confidence and since."""

    def test_expired_checkpoint_excluded_unless_asked(self, vault: Path, backend) -> None:
        _memory_note(vault, "agents/old/checkpoint.md",
                     updated="2025-01-01T00:00:00+00:00", ttl_days=30, confidence=0.9)
        fake = [{"path": "agents/old/checkpoint.md", "title": "Old", "score": 0.9, "text": "old"}]
        assert "agents/old/checkpoint.md" not in _recall(vault, backend, fake)
        assert "agents/old/checkpoint.md" in _recall(vault, backend, fake, include_expired=True)

    def test_fresh_checkpoint_kept(self, vault: Path, backend) -> None:
        path = memory_checkpoint("s1", "a", "summary", vault, ttl_days=1, backend=backend)
        fake = [{"path": path, "title": "C", "score": 0.9, "text": "summary"}]
        assert path in _recall(vault, backend, fake)

    def test_higher_confidence_ranks_first(self, vault: Path, backend) -> None:
        now = "2099-01-01T00:00:00+00:00"
        _memory_note(vault, "agents/low/checkpoint.md", updated=now, ttl_days=30, confidence=0.2)
        _memory_note(vault, "agents/high/checkpoint.md", updated=now, ttl_days=30, confidence=0.95)
        fake = [
            {"path": "agents/low/checkpoint.md", "title": "Low", "score": 0.8, "text": "x"},
            {"path": "agents/high/checkpoint.md", "title": "High", "score": 0.8, "text": "y"},
        ]
        out = _recall(vault, backend, fake)
        assert out.index("agents/high/") < out.index("agents/low/")

    def test_since_passed_to_search(self, vault: Path, backend) -> None:
        with patch("alaya.tools.search._hybrid_search_available", return_value=True), \
             patch("alaya.tools.search._run_corrective_search", return_value=[]) as mock:
            memory_recall("q", vault, since="2026-11-01", backend=backend)
        assert mock.call_args.kwargs["since"] == "2026-11-01"

    def test_ordinary_notes_rank_as_before(self, vault: Path, backend) -> None:
        fake = [
            {"path": "ideas/b.md", "title": "B", "score": 0.5, "text": "b"},
            {"path": "ideas/a.md", "title": "A", "score": 0.9, "text": "a"},
        ]
        out = _recall(vault, backend, fake)
        assert out.index("ideas/b.md") < out.index("ideas/a.md")
        assert "(score 0.50)" in out and "(score 0.90)" in out


def _note(vault: Path, rel: str, body: str = "body", fm: str | None = None) -> str:
    """A note titled as its file stem, so its link key is the same on zk and Obsidian."""
    path = vault / rel
    fm = fm if fm is not None else f"title: {path.stem}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{fm}---\n\n{body}\n")
    return rel


class TestMemorySupersede:
    """#171: mark old memory replaced instead of overwriting it."""

    def test_recall_returns_new_not_old(self, vault: Path, backend) -> None:
        _note(vault, "decisions/db-old.md", "Use MySQL.")
        _note(vault, "decisions/db-new.md", "Use Postgres.")
        memory_supersede("decisions/db-old.md", "decisions/db-new.md", vault,
                         reason="MySQL lacks\nwhat we need", backend=backend)
        fake = [
            {"path": "decisions/db-old.md", "title": "Old", "score": 0.9, "text": "Use MySQL."},
            {"path": "decisions/db-new.md", "title": "New", "score": 0.8, "text": "Use Postgres."},
        ]
        out = _recall(vault, backend, fake)
        assert "db-new.md" in out and "db-old.md" not in out

        both = _recall(vault, backend, fake, include_superseded=True)
        assert "`decisions/db-old.md` (score 0.90) — superseded by [[db-new]]" in both
        assert "db-new.md" in both

    def test_writes_valid_frontmatter_both_ways(self, vault: Path, backend) -> None:
        import yaml

        _note(vault, "a.md", fm="title: a\ntags:\n  - x\n")
        _note(vault, "b.md", fm='title: b\nsupersedes: ["[[z]]"]\n')
        memory_supersede("a.md", "[[b]]", vault, reason="changed", backend=backend)
        memory_supersede("a.md", "b.md", vault, backend=backend)  # idempotent on the list

        a, b = (vault / "a.md").read_text(), (vault / "b.md").read_text()
        meta_a = yaml.safe_load(a.split("---")[1])
        meta_b = yaml.safe_load(b.split("---")[1])
        assert meta_a == {"title": "a", "tags": ["x"], "superseded_by": "[[b]]"}
        assert meta_b["supersedes"] == ["[[z]]", "[[a]]"]
        assert "> Superseded by [[b]] on " in a and ": changed" in a

    def test_links_resolve_in_graph(self, vault: Path, backend) -> None:
        _note(vault, "a.md")
        _note(vault, "b.md")
        memory_supersede("a.md", "b.md", vault, backend=backend)
        assert backend.resolve_wikilink("b").resolve() == (vault / "b.md").resolve()
        assert backend.resolve_wikilink("a").resolve() == (vault / "a.md").resolve()
        from alaya.index.graph_rag import _WIKILINK_RE
        assert "b" in _WIKILINK_RE.findall((vault / "a.md").read_text())
        assert "a" in _WIKILINK_RE.findall((vault / "b.md").read_text())

    def test_note_without_frontmatter_gets_one(self, vault: Path, backend) -> None:
        (vault / "plain.md").write_text("# Plain\n\ntext\n")  # no frontmatter
        _note(vault, "b.md")
        memory_supersede("plain.md", "b.md", vault, backend=backend)
        assert (vault / "plain.md").read_text().startswith('---\nsuperseded_by: "[[b]]"\n---\n\n# Plain')

    def test_rejects_self_missing_and_escaping(self, vault: Path, backend) -> None:
        _note(vault, "a.md")
        with pytest.raises(ValueError):
            memory_supersede("a.md", "a.md", vault, backend=backend)
        with pytest.raises(FileNotFoundError):
            memory_supersede("a.md", "nope.md", vault, backend=backend)
        with pytest.raises(ValueError):
            memory_supersede("../outside.md", "a.md", vault, backend=backend)

    def test_emits_events_for_both(self, vault: Path, backend) -> None:
        from alaya.events import on_note_change, _listeners
        _note(vault, "a.md")
        _note(vault, "b.md")
        seen = []
        on_note_change(seen.append)
        try:
            memory_supersede("a.md", "b.md", vault, backend=backend)
        finally:
            _listeners.remove(seen.append)
        assert sorted(e.path for e in seen) == ["a.md", "b.md"]

    def test_checkpoint_supersedes(self, vault: Path, backend) -> None:
        _note(vault, "agents/old/checkpoint.md")
        path = memory_checkpoint("new", "a", "s", vault, supersedes=["agents/old/checkpoint.md"], backend=backend)
        assert 'superseded_by: "[[' in (vault / "agents/old/checkpoint.md").read_text()
        assert "supersedes:" in (vault / path).read_text()

    def test_checkpoint_with_missing_supersedes_writes_nothing(self, vault: Path, backend) -> None:
        with pytest.raises(FileNotFoundError):
            memory_checkpoint("new", "a", "s", vault, supersedes=["missing.md"], backend=backend)
        assert not (vault / "agents/new/checkpoint.md").exists()


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
            "memory_supersede_tool",
        }

    @pytest.mark.asyncio
    async def test_invalid_argument_returns_error_string(self, vault: Path, backend) -> None:
        test_mcp = FastMCP(name="alaya-test")
        memory._register(test_mcp, vault, backend=backend)
        tool = {t.name: t for t in await test_mcp.list_tools()}["memory_checkpoint_tool"]
        out = tool.fn(session_id="../nope", agent="a", summary_md="s")
        assert out.startswith("ERROR [")
