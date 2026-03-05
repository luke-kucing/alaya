"""Tests for server startup checks."""
import subprocess
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from alaya.server import _maybe_start_reembed
from alaya.backend.zk import ZkBackend
from alaya.backend.protocol import VaultConfig, LinkResolution


def test_zk_backend_check_available_succeeds():
    config = VaultConfig(
        root=Path("/tmp/test"),
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    backend = ZkBackend(config)
    mock_result = subprocess.CompletedProcess(args=["zk", "--version"], returncode=0, stdout="zk 0.14.0\n", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        backend.check_available()  # should not raise


def test_zk_backend_check_available_raises_when_not_installed():
    config = VaultConfig(
        root=Path("/tmp/test"),
        vault_type="zk",
        data_dir_name=".zk",
        link_resolution=LinkResolution.TITLE,
    )
    backend = ZkBackend(config)
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="zk CLI not found"):
            backend.check_available()


def test_maybe_start_reembed_no_op_when_models_match(tmp_path: Path) -> None:
    store = MagicMock()
    with patch("alaya.index.store.get_index_model", return_value="model-a"), \
         patch("alaya.index.models.get_active_model") as mock_active:
        mock_active.return_value.key = "model-a"
        threads_before = threading.active_count()
        _maybe_start_reembed(tmp_path, store)
        assert threading.active_count() == threads_before


def test_maybe_start_reembed_no_op_when_index_empty(tmp_path: Path) -> None:
    store = MagicMock()
    with patch("alaya.index.store.get_index_model", return_value=None), \
         patch("alaya.index.models.get_active_model") as mock_active:
        mock_active.return_value.key = "model-a"
        threads_before = threading.active_count()
        _maybe_start_reembed(tmp_path, store)
        assert threading.active_count() == threads_before


def test_maybe_start_reembed_spawns_thread_on_mismatch(tmp_path: Path) -> None:
    store = MagicMock()
    started = []

    def fake_reembed(*args, **kwargs):
        started.append(True)

    with patch("alaya.index.store.get_index_model", return_value="old-model"), \
         patch("alaya.index.models.get_active_model") as mock_active, \
         patch("alaya.index.reindex.reembed_background", side_effect=fake_reembed):
        mock_active.return_value.key = "new-model"
        _maybe_start_reembed(tmp_path, store)
        import time; time.sleep(0.05)

    assert started
