"""Graph RAG: augment vector search results with wikilink graph traversal.

Traverses 1-hop links (both outgoing and incoming) from initial search results
to find related notes that pure vector similarity might miss.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from alaya.vault import parse_note, iter_vault_md
from alaya.backend.protocol import LinkResolution

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def _build_link_index(
    vault: Path,
    link_resolution: LinkResolution = LinkResolution.TITLE,
    cache=None,
) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Build outgoing links and key->path lookup for the vault.

    Returns (outlinks, key_to_path) where:
    - outlinks[path] = set of linked keys (titles or filename stems)
    - key_to_path[key] = path
    """
    if cache:
        outlinks: dict[str, set[str]] = {}
        key_to_path: dict[str, str] = {}
        for n in cache.iter_notes():
            if link_resolution == LinkResolution.FILENAME:
                key = n.stem
            else:
                key = n.title or n.stem
            key_to_path[key] = n.path
            outlinks[n.path] = set(n.outlinks)
        return outlinks, key_to_path

    outlinks: dict[str, set[str]] = {}
    key_to_path: dict[str, str] = {}

    for md_file in iter_vault_md(vault):
        rel = str(md_file.relative_to(vault))
        try:
            content = md_file.read_text()
        except OSError:
            continue

        note = parse_note(content)
        if link_resolution == LinkResolution.FILENAME:
            key = md_file.stem
        else:
            key = note.title or md_file.stem
        key_to_path[key] = rel

        links = set()
        for match in _WIKILINK_RE.finditer(content):
            links.add(match.group(1).strip())
        outlinks[rel] = links

    return outlinks, key_to_path


def _invert_links(outlinks: dict[str, set[str]], key_to_path: dict[str, str]) -> dict[str, set[str]]:
    """Build inlinks: for each path, which paths link TO it."""
    inlinks: dict[str, set[str]] = {}
    for src_path, targets in outlinks.items():
        for target_key in targets:
            target_path = key_to_path.get(target_key)
            if target_path:
                inlinks.setdefault(target_path, set()).add(src_path)
    return inlinks


def expand_with_graph(
    results: list[dict],
    vault: Path,
    max_expansion: int = 5,
    link_resolution: LinkResolution = LinkResolution.TITLE,
    cache=None,
) -> list[dict]:
    """Augment search results by traversing 1-hop wikilinks.

    For each result, finds notes that link to it (backlinks) and notes it
    links to (outlinks). Adds unique linked notes to the results with a
    decayed score.

    Args:
        results: initial search results with {path, title, directory, score, text}
        vault: vault root path
        max_expansion: max number of graph-discovered notes to add
        link_resolution: how wikilinks map to note files

    Returns:
        Combined results (original + graph-expanded), sorted by score.
    """
    if not results:
        return results

    outlinks, key_to_path = _build_link_index(vault, link_resolution, cache=cache)
    inlinks = _invert_links(outlinks, key_to_path)

    result_paths = {r["path"] for r in results}
    candidates: dict[str, float] = {}  # path -> score

    # For each search result, find linked notes
    for r in results:
        path = r["path"]
        base_score = r.get("score", 0.0)
        # Decay factor: graph-discovered notes get a fraction of the parent's score
        graph_score = base_score * 0.5

        # Outgoing links from this note
        for target_key in outlinks.get(path, set()):
            target_path = key_to_path.get(target_key)
            if target_path and target_path not in result_paths:
                candidates[target_path] = max(candidates.get(target_path, 0), graph_score)

        # Incoming links to this note
        for src_path in inlinks.get(path, set()):
            if src_path not in result_paths:
                candidates[src_path] = max(candidates.get(src_path, 0), graph_score)

    if not candidates:
        return results

    # Sort candidates by score and take top N
    sorted_candidates = sorted(candidates.items(), key=lambda x: x[1], reverse=True)[:max_expansion]

    # Build result entries for graph-discovered notes
    path_to_key = {v: k for k, v in key_to_path.items()}
    expanded = []
    for path, score in sorted_candidates:
        title = path_to_key.get(path, Path(path).stem)
        directory = path.split("/")[0] if "/" in path else ""
        expanded.append({
            "path": path,
            "title": title,
            "directory": directory,
            "score": round(score, 3),
            "text": "",  # no chunk text for graph-expanded results
        })

    combined = results + expanded
    combined.sort(key=lambda r: r.get("score", 0), reverse=True)
    return combined
