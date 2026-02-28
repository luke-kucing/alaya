import shutil
from pathlib import Path

import pytest


VAULT_FIXTURE_PATH = Path(__file__).parent.parent / "vault_fixture"
VAULT_FIXTURE_LARGE_PATH = Path(__file__).parent.parent / "vault_fixture_large"


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


@pytest.fixture(scope="session")
def large_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copy vault_fixture_large to a session-scoped temp directory.

    Session-scoped so the expensive reindex only needs to run once per
    integration test session.
    """
    vault_path = tmp_path_factory.mktemp("large_vault") / "notes"
    shutil.copytree(VAULT_FIXTURE_LARGE_PATH, vault_path)
    return vault_path
