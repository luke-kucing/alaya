"""Unit tests for vault_graph tool."""
import json
from pathlib import Path

import pytest

from alaya.tools.graph import vault_graph


def _make_vault(tmp_path: Path) -> Path:
    root = tmp_path / "graph_vault"
    root.mkdir()
    (root / "notes").mkdir()

    # hub: linked to by two others
    (root / "notes" / "hub.md").write_text(
        "---\ntitle: Hub\ndate: 2026-01-01\n---\nCentral note.\n"
    )
    (root / "notes" / "a.md").write_text(
        "---\ntitle: A\ndate: 2026-01-01\n---\nSee [[Hub]].\n"
    )
    (root / "notes" / "b.md").write_text(
        "---\ntitle: B\ndate: 2026-01-01\n---\nAlso [[Hub]] and [[A]].\n"
    )
    # orphan: no links in or out
    (root / "notes" / "orphan.md").write_text(
        "---\ntitle: Orphan\ndate: 2026-01-01\n---\nStands alone.\n"
    )
    return root


class TestVaultGraph:
    def test_returns_valid_json(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        result = vault_graph(vault)
        data = json.loads(result)
        assert "node_count" in data
        assert "edge_count" in data
        assert "orphan_count" in data

    def test_counts_nodes_and_edges(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        data = json.loads(vault_graph(vault))
        assert data["node_count"] == 4
        assert data["edge_count"] == 3  # Hub, Hub, A

    def test_detects_orphan(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        data = json.loads(vault_graph(vault))
        assert data["orphan_count"] == 1
        assert any("orphan" in p for p in data["orphans"])

    def test_detects_hub(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        data = json.loads(vault_graph(vault))
        assert data["hubs"][0]["title"] == "Hub"
        assert data["hubs"][0]["inlinks"] == 2

    def test_handles_wikilink_alias(self, tmp_path: Path) -> None:
        vault = tmp_path / "alias_vault"
        vault.mkdir()
        (vault / "target.md").write_text("---\ntitle: Target\ndate: 2026-01-01\n---\n")
        (vault / "source.md").write_text("---\ntitle: Source\ndate: 2026-01-01\n---\n[[Target|display text]]\n")
        data = json.loads(vault_graph(vault))
        assert data["edge_count"] == 1

    def test_empty_vault(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        data = json.loads(vault_graph(empty))
        assert data["node_count"] == 0
        assert data["orphan_count"] == 0

    def test_max_nodes_truncates(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        data = json.loads(vault_graph(vault, max_nodes=2))
        assert data["node_count"] <= 2
        assert data["truncated"] is True

    def test_directory_filter(self, tmp_path: Path) -> None:
        vault = _make_vault(tmp_path)
        data = json.loads(vault_graph(vault, directory="notes"))
        assert data["node_count"] == 4  # all are in notes/
