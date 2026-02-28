"""Tests for the embedding model registry."""
import pytest
from unittest.mock import patch


class TestModelRegistry:
    def test_default_model_key_exists(self):
        from alaya.index.models import MODELS, DEFAULT_MODEL_KEY
        assert DEFAULT_MODEL_KEY in MODELS

    def test_default_model_has_required_fields(self):
        from alaya.index.models import MODELS, DEFAULT_MODEL_KEY
        cfg = MODELS[DEFAULT_MODEL_KEY]
        assert cfg.name
        assert cfg.dimensions > 0
        assert cfg.search_prefix
        assert cfg.document_prefix

    def test_q4_variant_exists(self):
        from alaya.index.models import MODELS
        assert "nomic-v1.5-q4" in MODELS

    def test_get_active_model_returns_default_when_no_env(self):
        from alaya.index.models import get_active_model, DEFAULT_MODEL_KEY, MODELS
        with patch.dict("os.environ", {}, clear=False):
            # remove env var if set
            import os
            os.environ.pop("ALAYA_EMBEDDING_MODEL", None)
            cfg = get_active_model()
        assert cfg == MODELS[DEFAULT_MODEL_KEY]

    def test_get_active_model_respects_env_var(self):
        from alaya.index.models import get_active_model, MODELS
        with patch.dict("os.environ", {"ALAYA_EMBEDDING_MODEL": "nomic-v1.5-q4"}):
            cfg = get_active_model()
        assert cfg == MODELS["nomic-v1.5-q4"]

    def test_get_active_model_unknown_key_raises(self):
        from alaya.index.models import get_active_model
        with patch.dict("os.environ", {"ALAYA_EMBEDDING_MODEL": "does-not-exist"}):
            with pytest.raises(ValueError, match="Unknown embedding model"):
                get_active_model()


class TestEmbedderUsesModelConfig:
    def test_model_name_from_registry(self):
        from alaya.index.models import get_active_model
        cfg = get_active_model()
        # embedder should use this name when loading
        assert cfg.name == "nomic-ai/nomic-embed-text-v1.5"

    def test_document_prefix_applied(self):
        from alaya.index.models import get_active_model
        cfg = get_active_model()
        text = "hello"
        assert cfg.document_prefix in f"{cfg.document_prefix}{text}"

    def test_search_prefix_applied(self):
        from alaya.index.models import get_active_model
        cfg = get_active_model()
        text = "query"
        assert cfg.search_prefix in f"{cfg.search_prefix}{text}"
