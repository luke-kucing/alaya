"""Graph tool: vault_graph."""
import json
import re
from collections import Counter
from pathlib import Path

from fastmcp import FastMCP
from alaya.vault import parse_note
from alaya.vault import iter_vault_md as _iter_vault_md

# Matches [[Title]] and [[Title|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def vault_graph(vault: Path, directory: str = "", max_nodes: int = 200) -> str:
    """Return the vault's wikilink graph as JSON.

    Includes node count, edge count, orphan notes (nothing links to them),
    and hub notes (most linked-to). Useful for understanding knowledge topology.
    """
    nodes: dict[str, dict] = {}  # rel_path -> metadata
    edges: list[tuple[str, str]] = []  # (source_path, target_title)

    for md_file in _iter_vault_md(vault):
        rel = str(md_file.relative_to(vault))

        if directory and not rel.startswith(directory.rstrip("/") + "/"):
            continue
        if len(nodes) >= max_nodes:
            break

        try:
            content = md_file.read_text()
        except OSError:
            continue

        note = parse_note(content)
        top_dir = rel.split("/")[0] if "/" in rel else ""
        nodes[rel] = {
            "title": note.title or md_file.stem,
            "tags": note.tags,
            "directory": top_dir,
        }

        for match in _WIKILINK_RE.finditer(content):
            edges.append((rel, match.group(1).strip()))

    # Build title -> path lookup for resolving wikilinks
    title_to_path = {meta["title"]: path for path, meta in nodes.items()}

    # Resolve edges to paths where possible; count in-links per node
    inlink_counts: Counter = Counter()
    resolved_edges = []
    for src, target_title in edges:
        target_path = title_to_path.get(target_title)
        resolved_edges.append({"source": src, "target": target_path or target_title})
        if target_path:
            inlink_counts[target_path] += 1

    # Orphans: notes with zero inlinks AND zero outlinks to known nodes
    outlink_set = {src for src, _ in edges}
    orphans = [
        path for path in nodes
        if inlink_counts[path] == 0 and path not in outlink_set
    ]

    # Hubs: top 10 most linked-to
    hubs = [
        {"path": path, "title": nodes[path]["title"], "inlinks": count}
        for path, count in inlink_counts.most_common(10)
        if path in nodes
    ]

    truncated = len(nodes) >= max_nodes

    return json.dumps({
        "node_count": len(nodes),
        "edge_count": len(resolved_edges),
        "orphan_count": len(orphans),
        "orphans": orphans[:20],
        "hubs": hubs,
        "truncated": truncated,
    }, indent=2)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def vault_graph_tool(directory: str = "", max_nodes: int = 200) -> str:
        """Return the vault's wikilink graph as JSON. Finds orphan notes and hub topics.

        directory: limit to notes under this directory (optional).
        max_nodes: cap on nodes scanned (default 200).
        """
        return vault_graph(vault, directory=directory, max_nodes=max_nodes)
