"""Tests for two-phase confirmation on the destructive tools."""
from pathlib import Path

import pytest
from fastmcp import FastMCP

from alaya.backend.config import get_backend


@pytest.fixture(autouse=True)
def _required_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALAYA_CONFIRM_MODE", raising=False)
    monkeypatch.delenv("ALAYA_CONFIRM_TTL", raising=False)


@pytest.fixture
def tools(vault: Path):
    """Register the destructive tools and return them by name."""
    from alaya.tools import edit, inbox, read, structure

    mcp = FastMCP(name="alaya-test")
    backend = get_backend(vault)
    structure._register(mcp, vault, backend=backend)
    edit._register(mcp, vault, backend=backend)
    read._register(mcp, vault, backend=backend)
    inbox._register(mcp, vault)

    import asyncio
    return {t.name: t.fn for t in asyncio.run(mcp.list_tools())}


def _token_from(proposal: str) -> str:
    return proposal.split('confirm_token="')[1].split('"')[0]


class TestDeleteNote:
    def test_first_call_previews_without_deleting(self, vault: Path, tools) -> None:
        out = tools["delete_note_tool"](path="projects/second-brain.md")
        assert "CONFIRM REQUIRED" in out
        assert (vault / "projects/second-brain.md").exists()

    def test_second_call_with_token_executes(self, vault: Path, tools) -> None:
        proposal = tools["delete_note_tool"](path="projects/second-brain.md")
        out = tools["delete_note_tool"](
            path="projects/second-brain.md", confirm_token=_token_from(proposal)
        )
        assert "ERROR" not in out
        assert not (vault / "projects/second-brain.md").exists()

    def test_token_for_another_note_is_rejected(self, vault: Path, tools) -> None:
        proposal = tools["delete_note_tool"](path="projects/second-brain.md")
        out = tools["delete_note_tool"](
            path="resources/kubernetes-notes.md", confirm_token=_token_from(proposal)
        )
        assert out.startswith("ERROR")
        assert (vault / "resources/kubernetes-notes.md").exists()

    def test_preview_lists_notes_left_with_broken_links(self, vault: Path, tools) -> None:
        out = tools["delete_note_tool"](path="resources/kubernetes-notes.md")
        assert "link to this one" in out


class TestRenameNote:
    def test_preview_lists_every_note_whose_wikilinks_change(self, vault: Path, tools) -> None:
        out = tools["rename_note_tool"](
            path="resources/kubernetes-notes.md", new_title="K8s Notes"
        )
        assert "Wikilinks rewritten" in out or "No other note links" in out
        assert (vault / "resources/kubernetes-notes.md").exists()

    def test_token_executes_the_rename(self, vault: Path, tools) -> None:
        proposal = tools["rename_note_tool"](
            path="resources/kubernetes-notes.md", new_title="K8s Notes"
        )
        out = tools["rename_note_tool"](
            path="resources/kubernetes-notes.md",
            new_title="K8s Notes",
            confirm_token=_token_from(proposal),
        )
        assert "ERROR" not in out
        assert (vault / "resources/k8s-notes.md").exists()

    def test_token_does_not_carry_to_a_different_title(self, vault: Path, tools) -> None:
        proposal = tools["rename_note_tool"](
            path="resources/kubernetes-notes.md", new_title="K8s Notes"
        )
        out = tools["rename_note_tool"](
            path="resources/kubernetes-notes.md",
            new_title="Something Else",
            confirm_token=_token_from(proposal),
        )
        assert out.startswith("ERROR")


class TestMoveNote:
    def test_preview_then_execute(self, vault: Path, tools) -> None:
        proposal = tools["move_note_tool"](path="ideas/voice-capture.md", destination="resources")
        assert "CONFIRM REQUIRED" in proposal
        assert (vault / "ideas/voice-capture.md").exists()

        tools["move_note_tool"](
            path="ideas/voice-capture.md", destination="resources",
            confirm_token=_token_from(proposal),
        )
        assert (vault / "resources/voice-capture.md").exists()


class TestReplaceSection:
    def test_preview_shows_a_diff(self, vault: Path, tools) -> None:
        note = vault / "ideas/sectioned.md"
        note.write_text("---\ntitle: Sectioned\n---\n\n## Notes\n\nold body\n")

        out = tools["replace_section_tool"](
            path="ideas/sectioned.md", section="Notes", new_content="new body"
        )
        assert "```diff" in out
        assert "old body" in note.read_text()

    def test_token_applies_the_replacement(self, vault: Path, tools) -> None:
        note = vault / "ideas/sectioned.md"
        note.write_text("---\ntitle: Sectioned\n---\n\n## Notes\n\nold body\n")

        proposal = tools["replace_section_tool"](
            path="ideas/sectioned.md", section="Notes", new_content="new body"
        )
        tools["replace_section_tool"](
            path="ideas/sectioned.md", section="Notes", new_content="new body",
            confirm_token=_token_from(proposal),
        )
        assert "new body" in note.read_text()


class TestClearInboxItem:
    def test_preview_shows_the_exact_line(self, vault: Path, tools) -> None:
        (vault / "inbox.md").write_text("# Inbox\n\n- 2026-02-23 09:15 buy milk\n")
        out = tools["clear_inbox_item_tool"](text="buy milk")
        assert "buy milk" in out
        assert "buy milk" in (vault / "inbox.md").read_text()

    def test_token_removes_the_line(self, vault: Path, tools) -> None:
        (vault / "inbox.md").write_text("# Inbox\n\n- 2026-02-23 09:15 buy milk\n")
        proposal = tools["clear_inbox_item_tool"](text="buy milk")
        tools["clear_inbox_item_tool"](text="buy milk", confirm_token=_token_from(proposal))
        assert "buy milk" not in (vault / "inbox.md").read_text()


class TestReindexVault:
    def test_preview_describes_the_work(self, vault: Path, tools) -> None:
        out = tools["reindex_vault_tool"]()
        assert "CONFIRM REQUIRED" in out
        assert "Incremental" in out

    def test_force_preview_warns_about_a_full_rebuild(self, vault: Path, tools) -> None:
        out = tools["reindex_vault_tool"](force=True)
        assert "FULL rebuild" in out

    def test_legacy_confirm_flag_still_works_when_disabled(
        self, vault: Path, tools, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "off")
        out = tools["reindex_vault_tool"](confirm=False)
        assert "requires confirm=True" in out


class TestOffMode:
    def test_destructive_tools_execute_directly(
        self, vault: Path, tools, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALAYA_CONFIRM_MODE", "off")
        out = tools["delete_note_tool"](path="projects/second-brain.md")
        assert "CONFIRM REQUIRED" not in out
        assert not (vault / "projects/second-brain.md").exists()
