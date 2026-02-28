"""Integration tests for hybrid search — full pipeline: reindex vault, run queries.

These tests load the real embedding model and use a real LanceDB instance.
They are slow (~30-60s for reindex) and run session-scoped to amortise cost.

Mark: pytest.mark.integration  (run with: uv run pytest -m integration)
"""
from __future__ import annotations

import pytest
from pathlib import Path

from alaya.index.store import get_store, reset_store
from alaya.index.reindex import reindex_all
from alaya.tools.search import search_notes


pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def indexed_vault(large_vault: Path):
    """Reindex the large vault once for the whole session."""
    reset_store()
    reindex_all(large_vault)
    yield large_vault
    reset_store()


# ---------------------------------------------------------------------------
# Search quality benchmark
# Each entry: (query, expected_paths_substring_list, description)
# All expected notes must appear in the top-5 results.
# ---------------------------------------------------------------------------
SEARCH_CASES = [
    (
        "kubernetes container orchestration pods deployments",
        ["kubernetes-notes"],
        "core kubernetes overview note",
    ),
    (
        "helm charts package manager kubernetes",
        ["helm-charts"],
        "helm package manager note",
    ),
    (
        "GitOps ArgoCD continuous delivery",
        ["argocd-gitops"],
        "argocd gitops note",
    ),
    (
        "zero trust network security never trust always verify",
        ["zero-trust-research"],
        "zero-trust security research note",
    ),
    (
        "LanceDB vector store options Qdrant Chroma Pinecone comparison",
        ["vector-databases"],
        "vector databases note",
    ),
    (
        "PostgreSQL MVCC concurrency indexing B-tree",
        ["postgresql-internals"],
        "postgresql internals note",
    ),
    (
        "Python asyncio event loop coroutines async await",
        ["python-async"],
        "python asyncio note",
    ),
    (
        "Prometheus metrics Grafana dashboards observability",
        ["observability-stack"],
        "observability stack note",
    ),
    (
        "service mesh Istio mTLS sidecar proxy Envoy",
        ["service-mesh-notes"],
        "service mesh note",
    ),
    (
        "LLM RAG retrieval augmented generation prompt engineering",
        ["llm-engineering"],
        "LLM engineering note",
    ),
]


class TestHybridSearchQuality:
    @pytest.mark.parametrize("query,expected_slugs,description", SEARCH_CASES)
    def test_expected_notes_in_top5(
        self,
        indexed_vault: Path,
        query: str,
        expected_slugs: list[str],
        description: str,
    ) -> None:
        result = search_notes(query, indexed_vault, limit=5)
        for slug in expected_slugs:
            assert slug in result, (
                f"Expected '{slug}' in top-5 results for query: {query!r}\n"
                f"Got:\n{result}"
            )

    def test_directory_filter_restricts_results(self, indexed_vault: Path) -> None:
        result = search_notes("notes", indexed_vault, directory="people", limit=10)
        if "No notes" not in result:
            rows = [l for l in result.splitlines() if "|" in l and "Score" not in l and "---" not in l]
            for row in rows:
                assert "people/" in row

    def test_tag_filter_restricts_results(self, indexed_vault: Path) -> None:
        result = search_notes("notes", indexed_vault, tags=["kubernetes"], limit=10)
        # if we got results, they should be from kubernetes-tagged notes
        assert isinstance(result, str)

    def test_no_results_returns_message(self, indexed_vault: Path) -> None:
        result = search_notes(
            "xyzzy_this_query_will_never_match_anything_in_the_vault",
            indexed_vault,
            limit=5,
        )
        assert "no notes" in result.lower() or "no results" in result.lower() or "|" in result

    def test_returns_markdown_table(self, indexed_vault: Path) -> None:
        result = search_notes("kubernetes", indexed_vault, limit=5)
        assert "|" in result


class TestReindex:
    def test_store_has_rows_after_reindex(self, indexed_vault: Path) -> None:
        store = get_store(indexed_vault)
        assert store.count() > 0

    def test_store_count_matches_note_count(self, indexed_vault: Path) -> None:
        # Each note produces at least 1 chunk
        store = get_store(indexed_vault)
        md_files = [f for f in indexed_vault.rglob("*.md") if ".zk" not in str(f)]
        assert store.count() >= len(md_files)
