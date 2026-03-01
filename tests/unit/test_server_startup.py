"""Tests for server startup checks."""
import subprocess
from unittest.mock import patch

import pytest

from alaya.server import _check_zk


def test_check_zk_succeeds_when_installed():
    mock_result = subprocess.CompletedProcess(args=["zk", "--version"], returncode=0, stdout="zk 0.14.0\n", stderr="")
    with patch("subprocess.run", return_value=mock_result):
        _check_zk()  # should not raise


def test_check_zk_exits_when_not_installed():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SystemExit) as exc_info:
            _check_zk()
        assert exc_info.value.code == 1
