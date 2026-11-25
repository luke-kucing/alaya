"""#146: GET /memory/context over the real FastMCP HTTP app."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from fastmcp import FastMCP
from starlette.testclient import TestClient

from alaya.tools import memory

ROWS = [
    {"path": "ideas/a.md", "title": "A", "score": np.float32(0.9), "text": "alpha", "chunk_id": 7},
    {"path": "ideas/b.md", "title": "B", "score": 0.5, "text": "beta", "superseded_by": "ideas/c.md"},
]


@pytest.fixture
def client(tmp_path: Path):
    mcp = FastMCP("t")
    memory._register(mcp, tmp_path)
    return TestClient(mcp.http_app())


def _get(client, params, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/memory/context", params=params, headers=headers)


def test_returns_projected_json(client, monkeypatch) -> None:
    monkeypatch.delenv("ALAYA_HTTP_TOKEN", raising=False)
    with patch.object(memory, "get_memory_context", return_value=ROWS) as mock:
        resp = _get(client, {"q": "hello", "k": "2"})
    assert resp.status_code == 200
    assert mock.call_args.args[0] == "hello" and mock.call_args.args[2] == 2
    rows = resp.json()["results"]
    assert rows[0] == {"path": "ideas/a.md", "title": "A", "score": pytest.approx(0.9), "text": "alpha"}
    assert rows[1]["superseded_by"] == "ideas/c.md"


def test_token_required_when_set(client, monkeypatch) -> None:
    monkeypatch.setenv("ALAYA_HTTP_TOKEN", "s3cret")
    with patch.object(memory, "get_memory_context", return_value=ROWS):
        assert _get(client, {"q": "x"}).status_code == 401
        assert _get(client, {"q": "x"}, token="nope").status_code == 401
        assert _get(client, {"q": "x"}, token="s3cret").status_code == 200


@pytest.mark.parametrize("params", [{}, {"q": " "}, {"q": "x", "k": "0"}, {"q": "x", "k": "99"}, {"q": "x", "k": "a"}])
def test_bad_params_400(client, monkeypatch, params) -> None:
    monkeypatch.delenv("ALAYA_HTTP_TOKEN", raising=False)
    assert _get(client, params).status_code == 400


def test_no_index_503(client, monkeypatch) -> None:
    monkeypatch.delenv("ALAYA_HTTP_TOKEN", raising=False)
    with patch.object(memory, "get_memory_context", return_value=None):
        assert _get(client, {"q": "x"}).status_code == 503
