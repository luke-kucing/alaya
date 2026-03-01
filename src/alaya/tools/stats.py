"""Stats tool: vault_stats."""
from collections import Counter
from pathlib import Path

from fastmcp import FastMCP
from alaya.vault import parse_note
from alaya.tools.structure import _iter_vault_md


def vault_stats(vault: Path) -> str:
    """Return a structured overview of the vault: note counts, directories, tags, index chunks."""
    md_files = list(_iter_vault_md(vault))
    total = len(md_files)

    if total == 0:
        return "Vault is empty — no notes found."

    # Notes per top-level directory
    dir_counts: Counter = Counter()
    tag_counts: Counter = Counter()

    for md_file in md_files:
        rel = md_file.relative_to(vault)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
        dir_counts[top_dir] += 1

        try:
            note = parse_note(md_file.read_text())
            for tag in note.tags:
                tag_counts[tag] += 1
        except OSError:
            pass

    # Index chunk count (best-effort; 0 if index not initialised)
    chunk_count = 0
    try:
        from alaya.index.store import get_store
        store = get_store(vault)
        chunk_count = len(store._get_table().search().limit(100_000).to_list())
    except Exception:
        pass

    lines = [f"Vault: {total} note{'s' if total != 1 else ''} across {len(dir_counts)} director{'ies' if len(dir_counts) != 1 else 'y'}"]
    if chunk_count:
        lines.append(f"Index: {chunk_count:,} chunks")
    lines.append("")

    lines.append("Notes by directory:")
    for d, count in sorted(dir_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {d:<20} {count}")

    if tag_counts:
        lines.append("")
        lines.append("Top tags:")
        for tag, count in tag_counts.most_common(15):
            lines.append(f"  #{tag:<19} {count}")

    return "\n".join(lines)


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def vault_stats_tool() -> str:
        """Return vault statistics: note counts by directory, top tags, and index coverage."""
        return vault_stats(vault)
