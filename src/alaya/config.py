import os
from pathlib import Path


class ConfigError(Exception):
    pass


def get_vault_root() -> Path:
    raw = os.environ.get("ZK_NOTEBOOK_DIR")
    if not raw:
        raise ConfigError("ZK_NOTEBOOK_DIR environment variable is not set")

    path = Path(raw).expanduser().resolve()

    if not path.exists():
        raise ConfigError(f"Vault root does not exist: {path}")

    if not (path / ".zk").exists():
        raise ConfigError(f"No .zk directory found at vault root: {path}. Run 'zk init' first.")

    return path


