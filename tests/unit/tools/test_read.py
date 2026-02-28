"""Unit tests for read tools — all zk calls are mocked."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.read import get_note, list_notes, get_backlinks, get_links, get_tags


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


class TestListNotes:
    def test_returns_markdown_table(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_LIST_OUTPUT.strip()):
            result = list_notes(vault)
        assert "|" in result  # markdown table
        assert "second-brain" in result

    def test_filter_by_dir(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, directory="projects")
        args = mock_zk.call_args[0][0]
        assert "projects" in args

    def test_filter_by_tag(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_LIST_OUTPUT.strip()) as mock_zk:
            list_notes(vault, tag="kubernetes")
        args = mock_zk.call_args[0][0]
        assert any("kubernetes" in a for a in args)

    def test_empty_vault_returns_message(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=""):
            result = list_notes(vault)
        assert "no notes" in result.lower()


class TestGetBacklinks:
    def test_returns_backlinks(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_BACKLINKS_OUTPUT.strip()):
            result = get_backlinks("projects/second-brain.md", vault)
        assert "second-brain" in result
        assert "2026-02-25" in result

    def test_no_backlinks_returns_message(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=""):
            result = get_backlinks("ideas/voice-capture.md", vault)
        assert "no backlinks" in result.lower()

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            get_backlinks("../../etc/passwd", vault)


class TestGetLinks:
    def test_returns_outgoing_links(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_LINKS_OUTPUT.strip()):
            result = get_links("projects/second-brain.md", vault)
        assert "kubernetes-notes" in result
        assert "platform-migration" in result

    def test_no_links_returns_message(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=""):
            result = get_links("ideas/voice-capture.md", vault)
        assert "no links" in result.lower()


class TestGetTags:
    def test_returns_all_tags_with_counts(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_TAGS_OUTPUT.strip()):
            result = get_tags(vault)
        assert "kubernetes" in result
        assert "3" in result

    def test_returns_markdown_table(self, vault: Path) -> None:
        with patch("alaya.tools.read.run_zk", return_value=ZK_TAGS_OUTPUT.strip()):
            result = get_tags(vault)
        assert "|" in result
