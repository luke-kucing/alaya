"""Tests for late chunking module."""
from unittest.mock import patch

from alaya.index.late_chunking import supports_late_chunking


class TestSupportsLateChunking:
    def test_nomic_does_not_support(self):
        # Default model is nomic which doesn't support late chunking
        assert supports_late_chunking() is False

    def test_jina_v3_supports(self):
        from alaya.index.models import MODELS
        with patch("alaya.index.late_chunking.get_active_model", return_value=MODELS["jina-v3"]):
            assert supports_late_chunking() is True
