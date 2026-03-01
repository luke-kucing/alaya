"""Vault path utilities shared across tools."""
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class NoteMeta:
    title: str
    date: str
    tags: list[str]
    extra: dict[str, str]
    body: str


def parse_note(content: str) -> NoteMeta:
    """Parse frontmatter + inline tags from note content."""
    raw_meta: dict[str, str] = {}
    body = content

    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            fm_block = content[3:end].strip()
            body = content[end + 4:].lstrip("\n")
            for line in fm_block.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    raw_meta[key.strip()] = val.strip()

    title = raw_meta.pop("title", "")
    date = raw_meta.pop("date", "")
    tags_raw = raw_meta.pop("tags", "")

    if tags_raw:
        tags = tags_raw.split()
    else:
        tags = _parse_inline_tags(body)

    return NoteMeta(title=title, date=date, tags=tags, extra=raw_meta, body=body)


def render_frontmatter(meta: dict) -> str:
    """Render a dict back to a YAML frontmatter block."""
    lines = ["---"]
    for key, val in meta.items():
        lines.append(f"{key}: {val}" if val else f"{key}:")
    lines.append("---\n")
    return "\n".join(lines)


_MAX_TAG_LINE_LEN = 500
_MAX_TAGS = 50


def _parse_inline_tags(body: str) -> list[str]:
    """Extract #hashtags from the first non-empty tag line.

    Lines longer than _MAX_TAG_LINE_LEN are skipped to avoid regex performance
    issues. Returns at most _MAX_TAGS tags.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > _MAX_TAG_LINE_LEN:
            break
        tags = re.findall(r"#([\w-]+)", stripped)
        # re.fullmatch avoids catastrophic backtracking from the repeated group
        if tags and re.fullmatch(r"(#[\w-]+ *)+", stripped):
            return tags[:_MAX_TAGS]
        break
    return []


# Top-level vault directories to skip during full-vault scans.
_SKIP_DIRS = {".zk", ".git", ".venv", "__pycache__"}


def iter_vault_md(vault: Path):
    """Yield .md files in vault, skipping tooling directories and unreadable files."""
    for md_file in vault.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in md_file.parts):
            continue
        yield md_file


def resolve_note_path(relative: str, vault: Path) -> Path:
    """Resolve a relative note path inside the vault.

    Raises ValueError if the path escapes the vault root (traversal attempt).
    """
    resolved = (vault / relative).resolve()
    try:
        resolved.relative_to(vault.resolve())
    except ValueError:
        raise ValueError(f"Path '{relative}' escapes vault root")
    return resolved
