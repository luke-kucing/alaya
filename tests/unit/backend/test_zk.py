"""ZkBackend unit tests: real fixture vault, run_zk mocked at subprocess boundary."""
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.backend.protocol import LinkResolution, VaultConfig, NoteEntry, LinkEntry, TagEntry
from alaya.backend.zk import ZkBackend


VAULT_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "vault_fixture"


@pytest.fixture
def zk_vault(tmp_path: Path) -> Path:
    """Copy the zk fixture vault to a temp directory."""
    vault_path = tmp_path / "zk_vault"
    shutil.copytree(VAULT_FIXTURE_PATH, vault_path)
    return vault_path


@pytest.fixture
def backend(zk_vault: Path) -> ZkBackend:
    config = VaultConfig(
        root=zk_vault,
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    return ZkBackend(config)


class TestListNotes:
    def test_parses_multiline_output_into_note_entries(self, backend: ZkBackend) -> None:
        output = (
            "projects/second-brain.md\tsecond-brain\t2026-02-23\t#project #python\n"
            "resources/kubernetes-notes.md\tkubernetes-notes\t2026-02-01\t#kubernetes"
        )
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.list_notes()

        assert len(entries) == 2
        assert all(isinstance(e, NoteEntry) for e in entries)
        assert entries[0].path == "projects/second-brain.md"
        assert entries[0].title == "second-brain"
        assert entries[0].date == "2026-02-23"
        assert entries[0].tags == "#project #python"
        assert entries[1].path == "resources/kubernetes-notes.md"

    def test_passes_tag_filter_to_zk(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.list_notes(tag="kubernetes")
        args = mock_zk.call_args[0][0]
        assert "--tag" in args
        idx = args.index("--tag")
        assert args[idx + 1] == "kubernetes"

    def test_passes_directory_filter_to_zk(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.list_notes(directory="projects")
        args = mock_zk.call_args[0][0]
        assert "projects" in args

    def test_passes_since_and_until_to_zk(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.list_notes(since="2026-01-01", until="2026-03-01")
        args = mock_zk.call_args[0][0]
        assert "--modified-after" in args
        assert "2026-01-01" in args
        assert "--modified-before" in args
        assert "2026-03-01" in args

    def test_passes_sort_to_zk(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.list_notes(sort="modified")
        args = mock_zk.call_args[0][0]
        assert "--sort" in args
        assert "modified" in args

    def test_passes_limit_to_zk(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.list_notes(limit=10)
        args = mock_zk.call_args[0][0]
        assert "--limit" in args
        idx = args.index("--limit")
        assert args[idx + 1] == "10"

    def test_returns_empty_on_zk_error(self, backend: ZkBackend) -> None:
        from alaya.zk import ZKError
        with patch("alaya.zk.run_zk", side_effect=ZKError("fail")):
            entries = backend.list_notes()
        assert entries == []

    def test_returns_empty_on_empty_output(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value=""):
            entries = backend.list_notes()
        assert entries == []

    def test_handles_missing_tsv_fields(self, backend: ZkBackend) -> None:
        """zk might return fewer fields than expected."""
        with patch("alaya.zk.run_zk", return_value="path.md\ttitle"):
            entries = backend.list_notes()
        assert len(entries) == 1
        assert entries[0].date == ""
        assert entries[0].tags == ""


class TestGetBacklinks:
    def test_parses_backlink_entries(self, backend: ZkBackend) -> None:
        output = "daily/2026-02-25.md\t2026-02-25\nprojects/brain.md\tBrain"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.get_backlinks("projects/second-brain.md")

        assert len(entries) == 2
        assert all(isinstance(e, LinkEntry) for e in entries)
        assert entries[0].path == "daily/2026-02-25.md"
        assert entries[0].title == "2026-02-25"

    def test_uses_path_as_title_fallback(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="orphan.md\t"):
            entries = backend.get_backlinks("some.md")
        assert entries[0].title == "orphan.md"

    def test_passes_link_to_flag(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.get_backlinks("projects/second-brain.md")
        args = mock_zk.call_args[0][0]
        assert "--link-to" in args
        assert "projects/second-brain.md" in args

    def test_returns_empty_on_error(self, backend: ZkBackend) -> None:
        from alaya.zk import ZKError
        with patch("alaya.zk.run_zk", side_effect=ZKError("fail")):
            assert backend.get_backlinks("x.md") == []


class TestGetOutlinks:
    def test_parses_outlink_entries(self, backend: ZkBackend) -> None:
        output = "resources/k8s.md\tKubernetes Notes"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.get_outlinks("projects/brain.md")

        assert len(entries) == 1
        assert isinstance(entries[0], LinkEntry)
        assert entries[0].path == "resources/k8s.md"
        assert entries[0].title == "Kubernetes Notes"

    def test_passes_linked_by_flag(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.get_outlinks("projects/brain.md")
        args = mock_zk.call_args[0][0]
        assert "--linked-by" in args
        assert "projects/brain.md" in args


class TestListTags:
    def test_parses_tag_entries_with_counts(self, backend: ZkBackend) -> None:
        output = "kubernetes\t3\nproject\t2\nmcp\t1"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.list_tags()

        assert len(entries) == 3
        assert all(isinstance(e, TagEntry) for e in entries)
        assert entries[0].name == "kubernetes"
        assert entries[0].count == 3
        assert entries[2].name == "mcp"
        assert entries[2].count == 1

    def test_handles_non_numeric_count(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="tag\tnotanumber"):
            entries = backend.list_tags()
        assert entries[0].count == 0


class TestKeywordSearch:
    def test_parses_search_results(self, backend: ZkBackend) -> None:
        output = "resources/k8s.md\tKubernetes\t2026-02-01"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.keyword_search("kubernetes")

        assert len(entries) == 1
        assert isinstance(entries[0], NoteEntry)
        assert entries[0].path == "resources/k8s.md"
        assert entries[0].title == "Kubernetes"
        assert entries[0].date == "2026-02-01"

    def test_passes_match_flag(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.keyword_search("helm charts")
        args = mock_zk.call_args[0][0]
        assert "--match" in args
        idx = args.index("--match")
        assert args[idx + 1] == "helm charts"

    def test_passes_tag_filters(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.keyword_search("test", tags=["k8s", "ref"])
        args = mock_zk.call_args[0][0]
        assert args.count("--tag") == 2

    def test_passes_since_filter(self, backend: ZkBackend) -> None:
        with patch("alaya.zk.run_zk", return_value="") as mock_zk:
            backend.keyword_search("test", since="2026-01-01")
        args = mock_zk.call_args[0][0]
        assert "--modified-after" in args
        assert "2026-01-01" in args


class TestResolveWikilink:
    def test_resolves_by_frontmatter_title(self, backend: ZkBackend, zk_vault: Path) -> None:
        result = backend.resolve_wikilink("second-brain")
        assert result is not None
        assert result.name == "second-brain.md"

    def test_returns_none_for_unknown(self, backend: ZkBackend) -> None:
        result = backend.resolve_wikilink("nonexistent-note-title")
        assert result is None


class TestNoteLinkKey:
    def test_returns_frontmatter_title(self, backend: ZkBackend) -> None:
        content = "---\ntitle: My Note Title\ndate: 2026-01-01\n---\nBody."
        assert backend.note_link_key(Path("ideas/my-note.md"), content) == "My Note Title"

    def test_falls_back_to_stem_without_frontmatter(self, backend: ZkBackend) -> None:
        content = "Just body, no frontmatter."
        assert backend.note_link_key(Path("ideas/my-note.md"), content) == "my-note"

    def test_falls_back_to_stem_with_empty_title(self, backend: ZkBackend) -> None:
        content = "---\ntitle:\ndate: 2026-01-01\n---\nBody."
        assert backend.note_link_key(Path("ideas/my-note.md"), content) == "my-note"


class TestParseFrontmatter:
    def test_extracts_title_and_date(self, backend: ZkBackend) -> None:
        content = "---\ntitle: Test\ndate: 2026-01-01\n---\nBody."
        meta = backend.parse_frontmatter(content)
        assert meta["title"] == "Test"
        assert meta["date"] == "2026-01-01"

    def test_extracts_inline_tags(self, backend: ZkBackend) -> None:
        content = "---\ntitle: Test\ndate: 2026-01-01\n---\n#tag1 #tag2\n\nBody."
        meta = backend.parse_frontmatter(content)
        assert "#tag1" in meta["tags"]
        assert "#tag2" in meta["tags"]

    def test_handles_no_frontmatter(self, backend: ZkBackend) -> None:
        content = "No frontmatter here."
        meta = backend.parse_frontmatter(content)
        assert meta["title"] == ""

    def test_preserves_extra_fields(self, backend: ZkBackend) -> None:
        content = "---\ntitle: Test\ndate: 2026-01-01\ncustom: value\n---\nBody."
        meta = backend.parse_frontmatter(content)
        assert meta["custom"] == "value"


class TestCheckAvailable:
    def test_succeeds_when_zk_installed(self, backend: ZkBackend) -> None:
        import subprocess
        mock_result = subprocess.CompletedProcess(
            args=["zk", "--version"], returncode=0, stdout="zk 0.14\n", stderr=""
        )
        with patch("subprocess.run", return_value=mock_result):
            backend.check_available()  # should not raise

    def test_raises_when_zk_missing(self, backend: ZkBackend) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="zk CLI not found"):
                backend.check_available()
