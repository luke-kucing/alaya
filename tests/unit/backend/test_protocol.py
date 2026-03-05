"""Protocol conformance tests: verify both backends satisfy VaultBackend."""
from pathlib import Path
from typing import runtime_checkable

import pytest

from alaya.backend.protocol import (
    LinkResolution,
    VaultBackend,
    VaultConfig,
)
from alaya.backend.zk import ZkBackend
from alaya.backend.obsidian import ObsidianBackend


def _make_config(tmp_path: Path, vault_type: str = "zk") -> VaultConfig:
    if vault_type == "zk":
        (tmp_path / ".zk").mkdir()
        return VaultConfig(
            root=tmp_path,
            vault_type="zk",
            data_dir_name=".zk",
            link_resolution=LinkResolution.TITLE,
        )
    else:
        (tmp_path / ".obsidian").mkdir()
        return VaultConfig(
            root=tmp_path,
            vault_type="obsidian",
            data_dir_name=".obsidian",
            link_resolution=LinkResolution.FILENAME,
        )


class TestProtocolConformance:
    """Both backends must implement all VaultBackend methods."""

    REQUIRED_METHODS = [
        "list_notes",
        "get_backlinks",
        "get_outlinks",
        "list_tags",
        "keyword_search",
        "resolve_wikilink",
        "parse_frontmatter",
        "render_frontmatter",
        "note_link_key",
        "check_available",
    ]

    def test_zk_backend_has_all_methods(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        backend = ZkBackend(config)
        for method_name in self.REQUIRED_METHODS:
            assert hasattr(backend, method_name), f"ZkBackend missing {method_name}"
            assert callable(getattr(backend, method_name))

    def test_obsidian_backend_has_all_methods(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "obsidian")
        backend = ObsidianBackend(config)
        for method_name in self.REQUIRED_METHODS:
            assert hasattr(backend, method_name), f"ObsidianBackend missing {method_name}"
            assert callable(getattr(backend, method_name))

    def test_both_backends_have_config_attribute(self, tmp_path: Path) -> None:
        zk_dir = tmp_path / "zk"
        zk_dir.mkdir()
        obs_dir = tmp_path / "obs"
        obs_dir.mkdir()
        zk = ZkBackend(_make_config(zk_dir, "zk"))
        obs = ObsidianBackend(_make_config(obs_dir, "obsidian"))
        assert isinstance(zk.config, VaultConfig)
        assert isinstance(obs.config, VaultConfig)


class TestVaultConfig:
    def test_vectors_dir_property(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        assert config.vectors_dir == tmp_path / ".zk" / "vectors"

    def test_index_state_path_property(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        assert config.index_state_path == tmp_path / ".zk" / "index_state.json"

    def test_audit_log_path_property(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        assert config.audit_log_path == tmp_path / ".zk" / "audit.jsonl"

    def test_obsidian_data_dir(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "obsidian")
        assert config.data_dir == tmp_path / ".obsidian"
        assert config.vectors_dir == tmp_path / ".obsidian" / "vectors"

    def test_default_skip_dirs(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        assert ".zk" in config.skip_dirs
        assert ".obsidian" in config.skip_dirs
        assert ".git" in config.skip_dirs
        assert ".trash" in config.skip_dirs

    def test_default_directory_map(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, "zk")
        assert config.directory_map["person"] == "people"
        assert config.directory_map["daily"] == "daily"
        assert config.directory_map["idea"] == "ideas"
