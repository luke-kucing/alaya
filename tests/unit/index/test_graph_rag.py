"""Tests for graph RAG: wikilink-based search expansion."""
from pathlib import Path
from unittest.mock import patch

from alaya.index.graph_rag import expand_with_graph, _build_link_index, _invert_links


def _write_note(vault: Path, rel_path: str, content: str) -> None:
    full = vault / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)


class TestExpandWithGraph:
    def test_expands_from_outgoing_links(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_note(vault, "resources/kubernetes.md", "---\ntitle: Kubernetes\n---\nSee [[Helm]] for charts.")
        _write_note(vault, "resources/helm.md", "---\ntitle: Helm\n---\nHelm chart packaging.")
        (vault / ".zk").mkdir()

        results = [
            {"path": "resources/kubernetes.md", "title": "Kubernetes", "directory": "resources", "score": 0.8, "text": "k8s"},
        ]
        expanded = expand_with_graph(results, vault)
        paths = [r["path"] for r in expanded]
        assert "resources/helm.md" in paths

    def test_expands_from_incoming_links(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_note(vault, "resources/kubernetes.md", "---\ntitle: Kubernetes\n---\nK8s content.")
        _write_note(vault, "projects/deploy.md", "---\ntitle: Deploy\n---\nUses [[Kubernetes]] for infra.")
        (vault / ".zk").mkdir()

        results = [
            {"path": "resources/kubernetes.md", "title": "Kubernetes", "directory": "resources", "score": 0.8, "text": "k8s"},
        ]
        expanded = expand_with_graph(results, vault)
        paths = [r["path"] for r in expanded]
        assert "projects/deploy.md" in paths

    def test_does_not_duplicate_existing_results(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_note(vault, "resources/kubernetes.md", "---\ntitle: Kubernetes\n---\nSee [[Helm]].")
        _write_note(vault, "resources/helm.md", "---\ntitle: Helm\n---\nHelm stuff.")
        (vault / ".zk").mkdir()

        results = [
            {"path": "resources/kubernetes.md", "title": "Kubernetes", "directory": "resources", "score": 0.8, "text": "k8s"},
            {"path": "resources/helm.md", "title": "Helm", "directory": "resources", "score": 0.7, "text": "helm"},
        ]
        expanded = expand_with_graph(results, vault)
        # Helm is already in results, should not be duplicated
        helm_count = sum(1 for r in expanded if r["path"] == "resources/helm.md")
        assert helm_count == 1

    def test_graph_score_is_decayed(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_note(vault, "resources/kubernetes.md", "---\ntitle: Kubernetes\n---\nSee [[Helm]].")
        _write_note(vault, "resources/helm.md", "---\ntitle: Helm\n---\nHelm stuff.")
        (vault / ".zk").mkdir()

        results = [
            {"path": "resources/kubernetes.md", "title": "Kubernetes", "directory": "resources", "score": 0.8, "text": "k8s"},
        ]
        expanded = expand_with_graph(results, vault)
        helm_result = next(r for r in expanded if r["path"] == "resources/helm.md")
        # Graph score should be 0.8 * 0.5 = 0.4
        assert helm_result["score"] == 0.4

    def test_empty_results_return_empty(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / ".zk").mkdir()
        assert expand_with_graph([], vault) == []

    def test_respects_max_expansion(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        links = " ".join(f"[[Note{i}]]" for i in range(10))
        _write_note(vault, "hub.md", f"---\ntitle: Hub\n---\n{links}")
        for i in range(10):
            _write_note(vault, f"note{i}.md", f"---\ntitle: Note{i}\n---\nContent {i}.")
        (vault / ".zk").mkdir()

        results = [
            {"path": "hub.md", "title": "Hub", "directory": "", "score": 0.9, "text": "hub"},
        ]
        expanded = expand_with_graph(results, vault, max_expansion=3)
        # 1 original + max 3 expanded
        assert len(expanded) <= 4


class TestBuildLinkIndex:
    def test_builds_outlinks_and_title_map(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        _write_note(vault, "a.md", "---\ntitle: Note A\n---\nLinks to [[Note B]].")
        _write_note(vault, "b.md", "---\ntitle: Note B\n---\nNo links.")
        (vault / ".zk").mkdir()

        outlinks, title_to_path = _build_link_index(vault)
        assert "Note B" in outlinks["a.md"]
        assert title_to_path["Note A"] == "a.md"
        assert title_to_path["Note B"] == "b.md"


class TestInvertLinks:
    def test_inverts_correctly(self) -> None:
        outlinks = {"a.md": {"B"}, "c.md": {"B"}}
        title_to_path = {"B": "b.md"}
        inlinks = _invert_links(outlinks, title_to_path)
        assert "a.md" in inlinks["b.md"]
        assert "c.md" in inlinks["b.md"]
