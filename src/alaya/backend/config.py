"""Vault type detection, config loading, and backend factory."""
from __future__ import annotations

import os
from pathlib import Path

from alaya.backend.protocol import LinkResolution, VaultConfig


class ConfigError(Exception):
    pass


def get_vault_root() -> Path:
    """Resolve the vault root from environment variables.

    Checks ALAYA_VAULT_DIR first, then falls back to ZK_NOTEBOOK_DIR for
    backward compatibility. Does NOT require .zk/ to exist — backend
    detection handles that.
    """
    raw = os.environ.get("ALAYA_VAULT_DIR") or os.environ.get("ZK_NOTEBOOK_DIR")
    if not raw:
        raise ConfigError(
            "Vault root not set. Set ALAYA_VAULT_DIR (or ZK_NOTEBOOK_DIR) environment variable."
        )

    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise ConfigError(f"Vault root does not exist: {path}")

    return path


def detect_vault_type(vault_root: Path) -> str:
    """Detect whether the vault is zk or Obsidian based on directory markers.

    Checks alaya.toml first for an explicit override, then falls back to
    directory detection (.zk/ or .obsidian/).
    """
    toml_config = _load_toml(vault_root)
    if toml_config:
        explicit = toml_config.get("vault", {}).get("type")
        if explicit in ("zk", "obsidian"):
            return explicit

    if (vault_root / ".zk").is_dir():
        return "zk"
    if (vault_root / ".obsidian").is_dir():
        return "obsidian"

    raise ConfigError(
        f"Cannot detect vault type at {vault_root}. "
        "Expected .zk/ or .obsidian/ directory, or an alaya.toml with [vault] type."
    )


def load_vault_config(vault_root: Path) -> VaultConfig:
    """Build a VaultConfig from detection + optional alaya.toml overrides."""
    vault_type = detect_vault_type(vault_root)
    toml_config = _load_toml(vault_root) or {}

    if vault_type == "zk":
        config = VaultConfig(
            root=vault_root,
            vault_type="zk",
            data_dir_name=".zk",
            link_resolution=LinkResolution.TITLE,
        )
    else:
        config = VaultConfig(
            root=vault_root,
            vault_type="obsidian",
            data_dir_name=".obsidian",
            link_resolution=LinkResolution.FILENAME,
        )

    # Apply alaya.toml overrides
    dirs = toml_config.get("directories", {})
    if dirs:
        mapping = dict(config.directory_map)
        for key in ("person", "idea", "project", "learning", "resource", "daily"):
            if key in dirs:
                mapping[key] = dirs[key]
        config.directory_map = mapping

    if "daily" in dirs:
        config.daily_dir = dirs["daily"]
    if "person" in dirs:
        config.people_dir = dirs["person"]

    settings = toml_config.get("settings", {})
    if "archives_dir" in settings:
        config.archives_dir = settings["archives_dir"]
    if "default_capture_dir" in settings:
        config.default_capture_dir = settings["default_capture_dir"]
    if "default_external_dir" in settings:
        config.default_external_dir = settings["default_external_dir"]

    return config


def get_backend(vault_root: Path) -> "VaultBackend":
    """Factory: detect vault type and return the appropriate backend instance."""
    config = load_vault_config(vault_root)

    if config.vault_type == "zk":
        from alaya.backend.zk import ZkBackend
        return ZkBackend(config)
    else:
        from alaya.backend.obsidian import ObsidianBackend
        return ObsidianBackend(config)


# Avoid circular imports: use TYPE_CHECKING for the protocol reference
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from alaya.backend.protocol import VaultBackend


def _load_toml(vault_root: Path) -> dict | None:
    """Load alaya.toml from vault root, returning None if absent."""
    toml_path = vault_root / "alaya.toml"
    if not toml_path.exists():
        return None
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    return tomllib.loads(toml_path.read_text())
