"""Unit tests for read tools — all zk calls are mocked."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.read import get_note, get_note_by_title, list_notes, get_backlinks, get_links, get_tags


ZK_LIST_OUTPUT = """\
projects/second-brain.md\tsecond-brain\t2026-02-23\t#project #python #mcp
resources/kubernetes-notes.md\tkubernetes-notes\t2026-02-01\t#kubernetes #reference
ideas/voice-capture.md\tvoice-capture\t2026-01-10\t#idea
"""

ZK_BACKLINKS_OUTPUT = """\
projects/second-brain.md\tsecond-brain
daily/2026-02-25.md\t2026-02-25
"""

ZK_LINKS_OUTPUT = """\
resources/kubernetes-notes.md\tkubernetes-notes
projects/platform-migration.md\tplatform-migration
"""

ZK_TAGS_OUTPUT = """\
kubernetes\t3
project\t2
idea\t1
mcp\t1
python\t1
reference\t1
"""


class TestGetNote:
    def test_returns_note_content(self, vault: Path) -> None:
        result = get_note("projects/second-brain.md", vault)
        assert "second-brain" in result
        assert "FastMCP" in result

    def test_returns_frontmatter_fields(self, vault: Path) -> None:
        result = get_note("projects/second-brain.md", vault)
        assert "title:" in result or "second-brain" in result
        assert "2026-02-23" in result

    def test_missing_note_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_note("projects/nonexistent.md", vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            get_note("../../etc/passwd", vault)

    # --- structured return (R-RD-02) ---

    def test_structured_return_has_metadata_header(self, vault: Path) -> None:
        result = get_note("projects/second-brain.md", vault)
        assert "**Title:**" in result
        assert "**Date:**" in result
        assert "**Path:**" in result

    def test_structured_return_has_content_separator(self, vault: Path) -> None:
        result = get_note("projects/second-brain.md", vault)
        assert "---" in result
        assert "FastMCP" in result  # body content follows separator

    def test_structured_return_includes_tags_when_present(self, vault: Path) -> None:
        result = get_note("projects/second-brain.md", vault)
        assert "**Tags:**" in result

    # --- title-based lookup (R-RD-01) ---

    def test_title_lookup_finds_note(self, vault: Path) -> None:
        result = get_note_by_title("second-brain", vault)
        assert "FastMCP" in result

    def test_title_lookup_case_insensitive(self, vault: Path) -> None:
        result = get_note_by_title("SECOND-BRAIN", vault)
        assert "FastMCP" in result

    def test_title_lookup_missing_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_note_by_title("this-note-does-not-exist", vault)

    def test_title_lookup_ambiguous_raises(self, vault: Path) -> None:
        """Two notes in the vault fixture share the 'platform' title fragment — use exact match."""
        # Create a second note with the same title to force ambiguity
        (vault / "ideas" / "second-brain-copy.md").write_text(
            "---\ntitle: second-brain\ndate: 2026-02-01\n---\nDuplicate.\n"
        )
        with pytest.raises(ValueError, match="[Aa]mbiguous"):
            get_note_by_title("second-brain", vault)


class TestListNotes:
    def test_returns_markdown_table(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()):
            result = list_notes(vault)
        assert "|" in result  # markdown table
        assert "second-brain" in result

    def test_filter_by_dir(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, directory="projects")
        args = mock_zk.call_args[0][0]
        assert "projects" in args

    def test_filter_by_tag(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, tag="kubernetes")
        args = mock_zk.call_args[0][0]
        assert any("kubernetes" in a for a in args)

    def test_empty_vault_returns_message(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            result = list_notes(vault)
        assert "no notes" in result.lower()

    # --- since / until / recent / sort (R-RD-03, R-SQ-02, R-SQ-04) ---

    def test_since_passes_modified_after_to_zk(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, since="2026-01-01")
        args = mock_zk.call_args[0][0]
        assert "--modified-after" in args
        assert "2026-01-01" in args

    def test_until_passes_modified_before_to_zk(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, until="2026-02-28")
        args = mock_zk.call_args[0][0]
        assert "--modified-before" in args
        assert "2026-02-28" in args

    def test_recent_converts_to_modified_after(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, recent=7)
        args = mock_zk.call_args[0][0]
        assert "--modified-after" in args
        idx = args.index("--modified-after")
        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=7)
        assert args[idx + 1] == cutoff.isoformat()

    def test_sort_passes_sort_flag_to_zk(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, sort="modified")
        args = mock_zk.call_args[0][0]
        assert "--sort" in args
        assert "modified" in args

    def test_recent_and_since_conflict_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="[Cc]onflict|not both|exclusive"):
            list_notes(vault, since="2026-01-01", recent=7)


class TestGetBacklinks:
    def test_returns_backlinks(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_BACKLINKS_OUTPUT.strip()):
            result = get_backlinks("projects/second-brain.md", vault)
        assert "second-brain" in result
        assert "2026-02-25" in result

    def test_no_backlinks_returns_message(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            result = get_backlinks("ideas/voice-capture.md", vault)
        assert "no backlinks" in result.lower()

    def test_uses_link_to_flag(self, vault: Path) -> None:
        # --link-to PATH finds notes linking TO PATH (i.e. backlinks)
        with patch("alaya.zk.run_zk", return_value=ZK_BACKLINKS_OUTPUT.strip()) as mock_zk:
            get_backlinks("projects/second-brain.md", vault)
        args = mock_zk.call_args[0][0]
        assert "--link-to" in args
        assert "--linked-by" not in args

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            get_backlinks("../../etc/passwd", vault)


class TestGetLinks:
    def test_returns_outgoing_links(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_LINKS_OUTPUT.strip()):
            result = get_links("projects/second-brain.md", vault)
        assert "kubernetes-notes" in result
        assert "platform-migration" in result

    def test_no_links_returns_message(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            result = get_links("ideas/voice-capture.md", vault)
        assert "no links" in result.lower()

    def test_uses_linked_by_flag(self, vault: Path) -> None:
        # --linked-by PATH finds notes linked by PATH (i.e. forward/outgoing links)
        with patch("alaya.zk.run_zk", return_value=ZK_LINKS_OUTPUT.strip()) as mock_zk:
            get_links("projects/second-brain.md", vault)
        args = mock_zk.call_args[0][0]
        assert "--linked-by" in args
        assert "--link-to" not in args


class TestGetTags:
    def test_returns_all_tags_with_counts(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_TAGS_OUTPUT.strip()):
            result = get_tags(vault)
        assert "kubernetes" in result
        assert "3" in result

    def test_returns_markdown_table(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=ZK_TAGS_OUTPUT.strip()):
            result = get_tags(vault)
        assert "|" in result


class TestRejectFlag:
    """_reject_flag must block values starting with '-' from entering zk args."""

    def test_directory_starting_with_dash_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="must not start with '-'"):
            list_notes(vault, directory="--help")

    def test_tag_starting_with_dash_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="must not start with '-'"):
            list_notes(vault, tag="--exec=rm -rf /")

    def test_sort_starting_with_dash_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="must not start with '-'"):
            list_notes(vault, sort="--version")

    def test_since_starting_with_dash_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="must not start with '-'"):
            list_notes(vault, since="--inject")

    def test_until_starting_with_dash_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="must not start with '-'"):
            list_notes(vault, until="--inject")

    def test_normal_directory_allowed(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            result = list_notes(vault, directory="projects")
        assert result == "No notes found."

    def test_normal_tag_allowed(self, vault: Path) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            result = list_notes(vault, tag="kubernetes")
        assert result == "No notes found."


class TestGetNotePaging:
    """offset/limit must page a note so successive calls reconstruct it."""

    def _write(self, vault: Path, lines: int = 120) -> str:
        note = vault / "ideas" / "long-note.md"
        body = "\n".join(f"line {i}" for i in range(lines))
        note.write_text(f"---\ntitle: Long Note\n---\n\n{body}\n")
        return "ideas/long-note.md"

    def _body_of(self, rendered: str) -> list[str]:
        """Body lines only: drop the header, the footer, and blank padding."""
        after = rendered.split("\n---\n", 1)[1]
        out = []
        for line in after.strip().splitlines():
            if line.startswith("…["):
                break
            if line.strip():
                out.append(line)
        return out

    def test_offset_skips_leading_lines(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        out = get_note(path, vault, offset=10, limit=5)
        assert self._body_of(out) == [f"line {i}" for i in range(10, 15)]

    def test_reports_the_line_range(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        out = get_note(path, vault, offset=10, limit=5)
        assert "**Lines:** 10-15 of 120" in out

    def test_points_at_the_next_page(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        out = get_note(path, vault, offset=0, limit=5)
        assert 'get_note(path="ideas/long-note.md", offset=5)' in out

    def test_last_page_has_no_continuation_marker(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault, lines=10)
        out = get_note(path, vault, offset=5, limit=5)
        assert "more line(s)" not in out

    def test_round_trip_reconstructs_the_note(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        collected: list[str] = []
        offset, page = 0, 25
        while True:
            rendered = get_note(path, vault, offset=offset, limit=page)
            body = self._body_of(rendered)
            if not body:
                break
            collected += body
            offset += len(body)
            if "more line(s)" not in rendered:
                break

        assert collected == [f"line {i}" for i in range(120)]

    def test_negative_offset_rejected(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        with pytest.raises(ValueError, match="offset"):
            get_note(path, vault, offset=-1)

    def test_zero_limit_rejected(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault)
        with pytest.raises(ValueError, match="limit"):
            get_note(path, vault, limit=0)

    def test_offset_past_end_returns_no_body(self, vault: Path) -> None:
        from alaya.tools.read import get_note

        path = self._write(vault, lines=5)
        assert self._body_of(get_note(path, vault, offset=99)) == []


class TestGetNoteCap:
    def test_long_note_is_truncated_with_a_resume_offset(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from alaya.tools.read import get_note

        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        note = vault / "ideas" / "huge.md"
        note.write_text("---\ntitle: Huge\n---\n\n" + "\n".join(f"filler line {i}" for i in range(500)))

        out = get_note("ideas/huge.md", vault)
        assert "line(s) truncated" in out
        assert 'get_note(path="ideas/huge.md", offset=' in out

    def test_unbounded_returns_everything(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from alaya.tools.read import get_note

        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        note = vault / "ideas" / "huge.md"
        note.write_text("---\ntitle: Huge\n---\n\n" + "\n".join(f"filler line {i}" for i in range(500)))

        out = get_note("ideas/huge.md", vault, unbounded=True)
        assert "truncated" not in out
        assert "filler line 499" in out

    def test_resume_offset_continues_correctly(
        self, vault: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from alaya.tools.read import get_note

        monkeypatch.setenv("ALAYA_MAX_TOOL_OUTPUT_TOKENS", "200")
        note = vault / "ideas" / "huge.md"
        note.write_text("---\ntitle: Huge\n---\n\n" + "\n".join(f"filler line {i}" for i in range(500)))

        first = get_note("ideas/huge.md", vault)
        resume = int(first.split("offset=")[1].split(")")[0])
        second = get_note("ideas/huge.md", vault, offset=resume)
        assert f"filler line {resume}" in second
