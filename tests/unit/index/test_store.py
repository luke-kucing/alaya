"""Unit tests for LanceDB store — DB operations use a real in-memory/tmp table."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from alaya.index.embedder import Chunk, chunk_note
from alaya.index.store import upsert_note, delete_note_from_index, hybrid_search, VaultStore, get_store, reset_store


def _make_chunks(path: str, text: str = "Some content about kubernetes and helm.") -> list[Chunk]:
    return [
        Chunk(
            path=path,
            title=path.split("/")[-1].replace(".md", ""),
            tags=["test"],
            directory=path.split("/")[0],
            modified_date="2026-02-01",
            chunk_index=0,
            text=text,
        )
    ]


def _fake_embeddings(chunks: list[Chunk]) -> list[np.ndarray]:
    return [np.random.rand(768).astype(np.float32) for _ in chunks]


class TestUpsertNote:
    def test_note_indexed_and_retrievable(self, vault: Path, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        chunks = _make_chunks("resources/kubernetes-notes.md")
        embeddings = _fake_embeddings(chunks)
        upsert_note("resources/kubernetes-notes.md", chunks, embeddings, store)
        assert store.count() == 1

    def test_upsert_replaces_existing_chunks(self, vault: Path, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        chunks_v1 = _make_chunks("resources/kubernetes-notes.md", "Version 1 content.")
        chunks_v2 = _make_chunks("resources/kubernetes-notes.md", "Version 2 content.")

        upsert_note("resources/kubernetes-notes.md", chunks_v1, _fake_embeddings(chunks_v1), store)
        upsert_note("resources/kubernetes-notes.md", chunks_v2, _fake_embeddings(chunks_v2), store)

        assert store.count() == 1  # replaced, not doubled

    def test_multiple_notes_indexed(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        for path in ["projects/second-brain.md", "resources/kubernetes-notes.md"]:
            chunks = _make_chunks(path)
            upsert_note(path, chunks, _fake_embeddings(chunks), store)
        assert store.count() == 2


class TestDeleteNoteFromIndex:
    def test_removes_chunks_for_path(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        chunks = _make_chunks("ideas/voice-capture.md")
        upsert_note("ideas/voice-capture.md", chunks, _fake_embeddings(chunks), store)
        assert store.count() == 1

        delete_note_from_index("ideas/voice-capture.md", store)
        assert store.count() == 0

    def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        # should not raise
        delete_note_from_index("ideas/ghost.md", store)

    def test_path_with_single_quote_does_not_crash(self, tmp_path: Path) -> None:
        # Single quotes in paths must be escaped to avoid malformed filter expressions.
        store = VaultStore(tmp_path / "lance")
        path = "ideas/it's-complicated.md"
        chunks = _make_chunks(path)
        upsert_note(path, chunks, _fake_embeddings(chunks), store)
        assert store.count() == 1
        # Must not raise or leave ghost entries
        delete_note_from_index(path, store)
        assert store.count() == 0


class TestHybridSearch:
    def test_returns_results(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        chunks = _make_chunks("resources/kubernetes-notes.md", "kubernetes helm charts argocd")
        embeddings = _fake_embeddings(chunks)
        upsert_note("resources/kubernetes-notes.md", chunks, embeddings, store)

        query_embedding = np.random.rand(768).astype(np.float32)
        results = hybrid_search("kubernetes", query_embedding, store, limit=5)
        assert isinstance(results, list)

    def test_empty_index_returns_empty(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        query_embedding = np.random.rand(768).astype(np.float32)
        results = hybrid_search("anything", query_embedding, store, limit=5)
        assert results == []

    def test_directory_filter_applied(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        for path, text in [
            ("resources/kubernetes-notes.md", "kubernetes content"),
            ("projects/second-brain.md", "project content"),
        ]:
            chunks = _make_chunks(path, text)
            upsert_note(path, chunks, _fake_embeddings(chunks), store)

        query_embedding = np.random.rand(768).astype(np.float32)
        results = hybrid_search("content", query_embedding, store, directory="resources", limit=5)
        for r in results:
            assert r["directory"] == "resources"

    def test_tags_filter_excludes_non_matching(self, tmp_path: Path) -> None:
        store = VaultStore(tmp_path / "lance")
        # kubernetes note has tag 'kubernetes'; project note has tag 'project'
        k_chunks = [Chunk(
            path="resources/kubernetes-notes.md",
            title="kubernetes-notes",
            tags=["kubernetes", "reference"],
            directory="resources",
            modified_date="2026-02-01",
            chunk_index=0,
            text="kubernetes helm charts",
        )]
        p_chunks = [Chunk(
            path="projects/second-brain.md",
            title="second-brain",
            tags=["project"],
            directory="projects",
            modified_date="2026-02-23",
            chunk_index=0,
            text="project planning content",
        )]
        upsert_note("resources/kubernetes-notes.md", k_chunks, _fake_embeddings(k_chunks), store)
        upsert_note("projects/second-brain.md", p_chunks, _fake_embeddings(p_chunks), store)

        query_embedding = np.random.rand(768).astype(np.float32)
        results = hybrid_search("content", query_embedding, store, tags=["kubernetes"], limit=5)
        # every result should come from the kubernetes note (tag filter applied)
        for r in results:
            assert "kubernetes" in r["path"]


class TestGetStore:
    def test_returns_same_instance_for_same_vault(self, tmp_path: Path) -> None:
        reset_store()
        s1 = get_store(tmp_path)
        s2 = get_store(tmp_path)
        assert s1 is s2

    def test_returns_different_instance_for_different_vault(self, tmp_path: Path) -> None:
        reset_store()
        vault_a = tmp_path / "vault_a"
        vault_b = tmp_path / "vault_b"
        vault_a.mkdir()
        vault_b.mkdir()
        s1 = get_store(vault_a)
        s2 = get_store(vault_b)
        assert s1 is not s2

    def test_reset_store_clears_cache(self, tmp_path: Path) -> None:
        reset_store()
        s1 = get_store(tmp_path)
        reset_store()
        s2 = get_store(tmp_path)
        assert s1 is not s2
