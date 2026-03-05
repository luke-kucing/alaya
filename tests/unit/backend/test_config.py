"""Tests for vault type detection and config loading."""
from pathlib import Path

import pytest

from alaya.backend.config import (
    ConfigError,
    detect_vault_type,
    get_vault_root,
    load_vault_config,
    get_backend,
)
from alaya.backend.protocol import LinkResolution


class TestDetectVaultType:
    def test_detects_zk(self, tmp_path: Path) -> None:
        (tmp_path / ".zk").mkdir()
        assert detect_vault_type(tmp_path) == "zk"

    def test_detects_obsidian(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        assert detect_vault_type(tmp_path) == "obsidian"

    def test_zk_wins_when_both_exist(self, tmp_path: Path) -> None:
        (tmp_path / ".zk").mkdir()
        (tmp_path / ".obsidian").mkdir()
        assert detect_vault_type(tmp_path) == "zk"

    def test_raises_when_neither(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="Cannot detect"):
            detect_vault_type(tmp_path)

    def test_alaya_toml_overrides_detection(self, tmp_path: Path) -> None:
        (tmp_path / ".zk").mkdir()
        (tmp_path / "alaya.toml").write_text('[vault]\ntype = "obsidian"\n')
        assert detect_vault_type(tmp_path) == "obsidian"

    def test_alaya_toml_explicit_zk(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / "alaya.toml").write_text('[vault]\ntype = "zk"\n')
        assert detect_vault_type(tmp_path) == "zk"


class TestLoadVaultConfig:
    def test_zk_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".zk").mkdir()
        config = load_vault_config(tmp_path)
        assert config.vault_type == "zk"
        assert config.data_dir_name == ".zk"
        assert config.link_resolution == LinkResolution.TITLE
        assert config.daily_dir == "daily"
        assert config.people_dir == "people"

    def test_obsidian_defaults(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        config = load_vault_config(tmp_path)
        assert config.vault_type == "obsidian"
        assert config.data_dir_name == ".obsidian"
        assert config.link_resolution == LinkResolution.FILENAME

    def test_toml_overrides_directories(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / "alaya.toml").write_text(
            '[directories]\n'
            'daily = "Daily Notes"\n'
            'person = "People"\n'
            'idea = "Notes"\n'
        )
        config = load_vault_config(tmp_path)
        assert config.daily_dir == "Daily Notes"
        assert config.people_dir == "People"
        assert config.directory_map["daily"] == "Daily Notes"
        assert config.directory_map["idea"] == "Notes"

    def test_toml_overrides_settings(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        (tmp_path / "alaya.toml").write_text(
            '[settings]\n'
            'archives_dir = "Archive"\n'
            'default_capture_dir = "Inbox"\n'
            'default_external_dir = "External"\n'
        )
        config = load_vault_config(tmp_path)
        assert config.archives_dir == "Archive"
        assert config.default_capture_dir == "Inbox"
        assert config.default_external_dir == "External"


class TestGetBackend:
    def test_returns_zk_backend_for_zk_vault(self, tmp_path: Path) -> None:
        (tmp_path / ".zk").mkdir()
        backend = get_backend(tmp_path)
        from alaya.backend.zk import ZkBackend
        assert isinstance(backend, ZkBackend)

    def test_returns_obsidian_backend_for_obsidian_vault(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        backend = get_backend(tmp_path)
        from alaya.backend.obsidian import ObsidianBackend
        assert isinstance(backend, ObsidianBackend)


class TestGetVaultRoot:
    def test_uses_alaya_vault_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ALAYA_VAULT_DIR", str(tmp_path))
        monkeypatch.delenv("ZK_NOTEBOOK_DIR", raising=False)
        assert get_vault_root() == tmp_path

    def test_falls_back_to_zk_notebook_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("ALAYA_VAULT_DIR", raising=False)
        monkeypatch.setenv("ZK_NOTEBOOK_DIR", str(tmp_path))
        assert get_vault_root() == tmp_path

    def test_alaya_vault_dir_takes_priority(self, tmp_path: Path, monkeypatch) -> None:
        dir1 = tmp_path / "vault1"
        dir2 = tmp_path / "vault2"
        dir1.mkdir()
        dir2.mkdir()
        monkeypatch.setenv("ALAYA_VAULT_DIR", str(dir1))
        monkeypatch.setenv("ZK_NOTEBOOK_DIR", str(dir2))
        assert get_vault_root() == dir1

    def test_raises_when_no_env_set(self, monkeypatch) -> None:
        monkeypatch.delenv("ALAYA_VAULT_DIR", raising=False)
        monkeypatch.delenv("ZK_NOTEBOOK_DIR", raising=False)
        with pytest.raises(ConfigError):
            get_vault_root()

    def test_raises_when_path_doesnt_exist(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ALAYA_VAULT_DIR", str(tmp_path / "nonexistent"))
        monkeypatch.delenv("ZK_NOTEBOOK_DIR", raising=False)
        with pytest.raises(ConfigError, match="does not exist"):
            get_vault_root()
