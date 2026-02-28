import shutil
from pathlib import Path

import pytest


VAULT_FIXTURE_PATH = Path(__file__).parent.parent / "vault_fixture"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Copy vault_fixture to a temp directory and return its path."""
    vault_path = tmp_path / "notes"
    shutil.copytree(VAULT_FIXTURE_PATH, vault_path)
    return vault_path


@pytest.fixture(autouse=True)
def set_vault_env(vault: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Set ZK_NOTEBOOK_DIR to the temp vault for every test."""
    monkeypatch.setenv("ZK_NOTEBOOK_DIR", str(vault))
