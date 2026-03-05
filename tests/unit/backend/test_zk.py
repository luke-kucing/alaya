"""ZkBackend unit tests: all zk CLI calls are mocked."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.backend.protocol import LinkResolution, VaultConfig
from alaya.backend.zk import ZkBackend


def _zk_backend(tmp_path: Path) -> ZkBackend:
    (tmp_path / ".zk").mkdir(exist_ok=True)
    config = VaultConfig(
        root=tmp_path,
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    return ZkBackend(config)


class TestListNotes:
    def test_parses_zk_output(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        output = "projects/brain.md\tBrain\t2026-02-23\t#project"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.list_notes()
        assert len(entries) == 1
        assert entries[0].path == "projects/brain.md"
        assert entries[0].title == "Brain"

    def test_returns_empty_on_zk_error(self, tmp_path: Path) -> None:
        from alaya.zk import ZKError
        backend = _zk_backend(tmp_path)
        with patch("alaya.zk.run_zk", side_effect=ZKError("fail")):
            entries = backend.list_notes()
        assert entries == []


class TestGetBacklinks:
    def test_parses_backlinks(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        output = "daily/2026-02-25.md\t2026-02-25"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.get_backlinks("projects/brain.md")
        assert len(entries) == 1
        assert entries[0].path == "daily/2026-02-25.md"

    def test_returns_empty_on_error(self, tmp_path: Path) -> None:
        from alaya.zk import ZKError
        backend = _zk_backend(tmp_path)
        with patch("alaya.zk.run_zk", side_effect=ZKError("fail")):
            entries = backend.get_backlinks("projects/brain.md")
        assert entries == []


class TestGetOutlinks:
    def test_parses_outlinks(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        output = "resources/k8s.md\tk8s notes"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.get_outlinks("projects/brain.md")
        assert len(entries) == 1
        assert entries[0].title == "k8s notes"


class TestListTags:
    def test_parses_tags(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        output = "kubernetes\t3\nproject\t2"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.list_tags()
        assert len(entries) == 2
        assert entries[0].name == "kubernetes"
        assert entries[0].count == 3


class TestKeywordSearch:
    def test_parses_search_results(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        output = "resources/k8s.md\tk8s\t2026-02-01"
        with patch("alaya.zk.run_zk", return_value=output):
            entries = backend.keyword_search("kubernetes")
        assert len(entries) == 1
        assert entries[0].path == "resources/k8s.md"


class TestNoteLinkKey:
    def test_returns_frontmatter_title(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        content = "---\ntitle: My Note Title\ndate: 2026-01-01\n---\nBody."
        assert backend.note_link_key(Path("ideas/my-note.md"), content) == "My Note Title"

    def test_falls_back_to_stem(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        content = "Just body, no frontmatter."
        assert backend.note_link_key(Path("ideas/my-note.md"), content) == "my-note"


class TestParseFrontmatter:
    def test_parses_zk_style(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        content = "---\ntitle: Test\ndate: 2026-01-01\n---\n#tag1 #tag2\n\nBody."
        meta = backend.parse_frontmatter(content)
        assert meta["title"] == "Test"
        assert meta["date"] == "2026-01-01"


class TestCheckAvailable:
    def test_succeeds_with_zk(self, tmp_path: Path) -> None:
        import subprocess
        backend = _zk_backend(tmp_path)
        mock_result = subprocess.CompletedProcess(args=["zk", "--version"], returncode=0, stdout="zk 0.14\n", stderr="")
        with patch("subprocess.run", return_value=mock_result):
            backend.check_available()

    def test_raises_when_missing(self, tmp_path: Path) -> None:
        backend = _zk_backend(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="zk CLI not found"):
                backend.check_available()
