"""#159: OpenAI-compatible embedding backend."""
import json

import httpx
import numpy as np
import pytest

from alaya.index import embedder, models, remote_embedder
from alaya.index.models import DEFAULT_MODEL_KEY, MODELS

DIMS = MODELS[DEFAULT_MODEL_KEY].dimensions
_RealClient = httpx.Client


@pytest.fixture
def server(monkeypatch):
    """Route every httpx.Client to a handler; returns the list of request bodies seen."""
    seen, state = [], {"handler": None}

    def default(request):
        body = json.loads(request.content)
        seen.append(body)
        n = len(body["input"])
        # reversed order on purpose: clients must sort by index
        data = [{"index": i, "embedding": [float(i + 1)] + [0.0] * (DIMS - 1)} for i in reversed(range(n))]
        return httpx.Response(200, json={"data": data})

    def route(request):
        return (state["handler"] or default)(request)

    monkeypatch.setattr(remote_embedder.httpx, "Client",
                        lambda **kw: _RealClient(transport=httpx.MockTransport(route), **kw))
    monkeypatch.setattr(remote_embedder, "_BACKOFF_SECONDS", 0)
    monkeypatch.setenv("ALAYA_EMBEDDING_URL", "http://mlx.local:8000/v1/")
    models._resolve_remote.cache_clear()
    embedder.reset_model()
    yield seen, state
    models._resolve_remote.cache_clear()
    embedder.reset_model()


def test_embed_batches_and_keeps_input_order(server):
    seen, _ = server
    client = remote_embedder.RemoteEmbedding("http://mlx.local:8000/v1", "m")
    out = list(client.embed(["a", "b", "c"], batch_size=2))
    assert [len(b["input"]) for b in seen] == [2, 1]
    assert [v[0] for v in out] == [1.0, 2.0, 1.0]
    assert all(v.dtype == np.float32 for v in out)


def test_retries_5xx_then_succeeds(server):
    _, state = server
    calls = []

    def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503)
        state["handler"] = None
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    state["handler"] = flaky
    assert len(list(remote_embedder.RemoteEmbedding("http://x", "m").embed(["a"]))) == 1
    assert len(calls) == 2


def test_client_error_is_not_retried(server):
    _, state = server
    calls = []
    state["handler"] = lambda r: calls.append(1) or httpx.Response(401)
    with pytest.raises(httpx.HTTPStatusError):
        list(remote_embedder.RemoteEmbedding("http://x", "m").embed(["a"]))
    assert len(calls) == 1


def test_active_model_uses_reachable_endpoint(server, monkeypatch):
    monkeypatch.setenv("ALAYA_EMBEDDING_REMOTE_MODEL", "nomic-embed-mlx")
    cfg = models.get_active_model()
    assert (cfg.backend, cfg.key, cfg.url) == ("openai", "openai:nomic-embed-mlx", "http://mlx.local:8000/v1")
    assert cfg.key != DEFAULT_MODEL_KEY  # distinct key: switching triggers the re-embed
    assert cfg.supports_late_chunking is False
    assert cfg.search_prefix == MODELS[DEFAULT_MODEL_KEY].search_prefix


def test_falls_back_to_local_when_unreachable(server):
    _, state = server

    def down(request):
        raise httpx.ConnectError("refused", request=request)

    state["handler"] = down
    assert models.get_active_model() is MODELS[DEFAULT_MODEL_KEY]


def test_falls_back_on_dimension_mismatch(server):
    _, state = server
    state["handler"] = lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
    assert models.get_active_model() is MODELS[DEFAULT_MODEL_KEY]


def test_embed_chunks_through_remote_backend(server):
    seen, _ = server
    chunks = [embedder.Chunk("p.md", "t", [], "", "", i, f"text {i}") for i in range(3)]
    vecs = embedder.embed_chunks(chunks)
    assert len(vecs) == 3 and all(abs(np.linalg.norm(v) - 1) < 1e-5 for v in vecs)
    assert seen[-1]["input"][0].startswith(MODELS[DEFAULT_MODEL_KEY].document_prefix)
    assert isinstance(embedder.get_model()[0], remote_embedder.RemoteEmbedding)
