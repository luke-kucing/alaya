"""Client for an OpenAI-compatible ``/embeddings`` endpoint (oMLX, vLLM, Ollama, OpenAI) (#159).

It has the same ``embed`` / ``query_embed`` shape as fastembed's ``TextEmbedding``, so the
embedder's call sites work unchanged with either backend.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Iterable, Iterator

import httpx
import numpy as np

logger = logging.getLogger(__name__)

_ATTEMPTS = 4
_BACKOFF_SECONDS = 0.5


class RemoteEmbedding:
    def __init__(self, url: str, model: str, client: httpx.Client | None = None) -> None:
        self._url = f"{url.rstrip('/')}/embeddings"
        self._model = model
        key = os.environ.get("ALAYA_EMBEDDING_API_KEY")
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._client = client or httpx.Client(timeout=120)

    def _post(self, texts: list[str]) -> list[list[float]]:
        """One request, retried with backoff on transport errors, 429 and 5xx."""
        for attempt in range(_ATTEMPTS):
            try:
                r = self._client.post(self._url, json={"model": self._model, "input": texts}, headers=self._headers)
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(f"{r.status_code} from {self._url}", request=r.request, response=r)
                r.raise_for_status()  # other 4xx: a config error, retrying won't help
                data = sorted(r.json()["data"], key=lambda d: d["index"])
                if len(data) != len(texts):
                    raise ValueError(f"{self._url} returned {len(data)} embeddings for {len(texts)} inputs")
                return [d["embedding"] for d in data]
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                retryable = not isinstance(e, httpx.HTTPStatusError) or e.response.status_code == 429 \
                    or e.response.status_code >= 500
                if not retryable or attempt == _ATTEMPTS - 1:
                    raise
                delay = _BACKOFF_SECONDS * 2**attempt
                logger.warning("Embedding request failed (%s); retrying in %.1fs", e, delay)
                time.sleep(delay)
        raise AssertionError("unreachable")

    def embed(self, texts: Iterable[str], batch_size: int = 64) -> Iterator[np.ndarray]:
        texts = list(texts)
        for i in range(0, len(texts), batch_size):
            for v in self._post(texts[i:i + batch_size]):
                yield np.asarray(v, dtype=np.float32)

    def query_embed(self, texts: Iterable[str]) -> Iterator[np.ndarray]:
        return self.embed(texts)
