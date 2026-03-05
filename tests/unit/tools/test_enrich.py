"""Tests for enrichment tools: LLM-powered chunk enhancement."""
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from alaya.tools.enrich import store_propositions, store_summary, enrich_chunk_context


class TestStorePropositions:
    def test_rejects_empty_propositions(self, vault: Path) -> None:
        result = store_propositions("test.md", [], vault)
        assert "ERROR" in result

    def test_stores_propositions_in_index(self, tmp_path: Path) -> None:
        from alaya.index.store import VaultStore

        store = VaultStore(tmp_path / "lance")
        # Set up a note in the store first
        from alaya.index.embedder import Chunk
        from alaya.index.store import upsert_note
        chunks = [Chunk(
            path="resources/k8s.md", title="k8s", tags=["devops"],
            directory="resources", modified_date="2026-03-01",
            chunk_index=0, text="Kubernetes content.",
        )]
        embeddings = [np.random.rand(768).astype(np.float32)]
        upsert_note("resources/k8s.md", chunks, embeddings, store)

        with patch("alaya.index.store.get_store", return_value=store), \
             patch("alaya.index.embedder.embed_chunks", return_value=[
                 np.random.rand(768).astype(np.float32),
                 np.random.rand(768).astype(np.float32),
             ]):
            result = store_propositions("resources/k8s.md", [
                "Kubernetes is a container orchestration platform.",
                "Kubernetes uses pods as the smallest deployable unit.",
            ], tmp_path)

        assert "2 propositions" in result
        # Original chunk should still be there
        assert store.count() == 3  # 1 original + 2 propositions


class TestStoreSummary:
    def test_rejects_empty_summary(self, vault: Path) -> None:
        result = store_summary(["a.md"], "", "Test Summary", vault)
        assert "ERROR" in result

    def test_stores_summary_in_index(self, tmp_path: Path) -> None:
        from alaya.index.store import VaultStore

        store = VaultStore(tmp_path / "lance")

        with patch("alaya.index.store.get_store", return_value=store), \
             patch("alaya.index.embedder.embed_chunks", return_value=[
                 np.random.rand(768).astype(np.float32),
             ]):
            result = store_summary(
                ["resources/k8s.md", "resources/helm.md"],
                "Both Kubernetes and Helm are used for container deployment.",
                "Container Deployment Overview",
                tmp_path,
            )

        assert "Container Deployment Overview" in result
        assert "2 notes" in result
        assert store.count() == 1


class TestEnrichChunkContext:
    def test_enriches_existing_chunk(self, tmp_path: Path) -> None:
        from alaya.index.store import VaultStore, upsert_note
        from alaya.index.embedder import Chunk

        store = VaultStore(tmp_path / "lance")
        chunks = [Chunk(
            path="resources/k8s.md", title="k8s", tags=[],
            directory="resources", modified_date="2026-03-01",
            chunk_index=0, text="Pods are the smallest unit.",
        )]
        embeddings = [np.random.rand(768).astype(np.float32)]
        upsert_note("resources/k8s.md", chunks, embeddings, store)

        with patch("alaya.index.store.get_store", return_value=store), \
             patch("alaya.index.embedder.embed_chunks", return_value=[
                 np.random.rand(768).astype(np.float32),
             ]):
            result = enrich_chunk_context(
                "resources/k8s.md", 0,
                "This chunk explains Kubernetes pod architecture.",
                tmp_path,
            )

        assert "Enriched" in result

    def test_rejects_missing_chunk(self, tmp_path: Path) -> None:
        from alaya.index.store import VaultStore

        store = VaultStore(tmp_path / "lance")

        with patch("alaya.index.store.get_store", return_value=store):
            result = enrich_chunk_context("ghost.md", 99, "context", tmp_path)

        assert "ERROR" in result
