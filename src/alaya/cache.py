"""VaultMetadataCache: in-memory metadata index for vault notes.

Eliminates redundant O(N) filesystem scans by caching frontmatter,
tags, wikilinks, and secondary lookup indices. Thread-safe and
invalidatable per-file for use with the file watcher.
"""
from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")

# Directories to skip during vault scans (matches vault.py _SKIP_DIRS).
_SKIP_DIRS = frozenset({".zk", ".obsidian", ".git", ".venv", "__pycache__", ".trash"})


@dataclass(slots=True)
class CachedNote:
    path: str
    title: str
    date: str
    tags: list[str]
    outlinks: set[str]
    stem: str
    mtime: float


class VaultMetadataCache:
    """In-memory metadata cache for all .md files in a vault.

    Lazily warmed on first access. Thread-safe via RLock.
    """

    def __init__(self, vault: Path, skip_dirs: frozenset[str] = _SKIP_DIRS) -> None:
        self._vault = vault
        self._skip_dirs = skip_dirs
        self._notes: dict[str, CachedNote] = {}
        self._title_index: dict[str, str] = {}   # lowercase title -> rel path
        self._stem_index: dict[str, str] = {}     # filename stem -> rel path
        self._warmed = False
        self._lock = threading.RLock()

    # -- Lazy init --

    def _ensure_warm(self) -> None:
        if self._warmed:
            return
        with self._lock:
            if not self._warmed:
                self.warm()

    def warm(self) -> None:
        """Scan the full vault and populate the cache."""
        notes: dict[str, CachedNote] = {}
        title_idx: dict[str, str] = {}
        stem_idx: dict[str, str] = {}

        for md_file in self._vault.rglob("*.md"):
            try:
                rel = str(md_file.relative_to(self._vault))
            except ValueError:
                continue
            if any(part in self._skip_dirs for part in Path(rel).parts):
                continue
            entry = self._read_note(md_file, rel)
            if entry is None:
                continue
            notes[rel] = entry
            title_idx[entry.title.lower()] = rel
            stem_idx[entry.stem] = rel

        with self._lock:
            self._notes = notes
            self._title_index = title_idx
            self._stem_index = stem_idx
            self._warmed = True

        logger.info("VaultMetadataCache warmed: %d notes", len(notes))

    # -- Single-file mutation --

    def invalidate(self, relative_path: str) -> None:
        """Re-read a single file and update cache + indices."""
        md_file = self._vault / relative_path
        with self._lock:
            # Remove old entry first
            self._remove_from_indices(relative_path)
            if md_file.exists():
                entry = self._read_note(md_file, relative_path)
                if entry is not None:
                    self._notes[relative_path] = entry
                    self._title_index[entry.title.lower()] = relative_path
                    self._stem_index[entry.stem] = relative_path

    def remove(self, relative_path: str) -> None:
        """Remove a file from the cache."""
        with self._lock:
            self._remove_from_indices(relative_path)

    def _remove_from_indices(self, relative_path: str) -> None:
        """Remove a path from all indices. Caller must hold _lock."""
        old = self._notes.pop(relative_path, None)
        if old is None:
            return
        # Only remove from secondary indices if they still point to this path
        if self._title_index.get(old.title.lower()) == relative_path:
            del self._title_index[old.title.lower()]
        if self._stem_index.get(old.stem) == relative_path:
            del self._stem_index[old.stem]

    # -- Accessors --

    def iter_notes(self) -> list[CachedNote]:
        """Return a snapshot list of all cached notes."""
        self._ensure_warm()
        with self._lock:
            return list(self._notes.values())

    def get_meta(self, relative_path: str) -> CachedNote | None:
        self._ensure_warm()
        with self._lock:
            return self._notes.get(relative_path)

    def title_to_path(self, title: str) -> str | None:
        """O(1) lookup by title (case-insensitive)."""
        self._ensure_warm()
        with self._lock:
            return self._title_index.get(title.lower())

    def stem_to_path(self, stem: str) -> str | None:
        """O(1) lookup by filename stem."""
        self._ensure_warm()
        with self._lock:
            return self._stem_index.get(stem)

    def get_outlinks(self, relative_path: str) -> set[str]:
        """Return the set of wikilink targets (raw text) for a note."""
        self._ensure_warm()
        with self._lock:
            entry = self._notes.get(relative_path)
            return set(entry.outlinks) if entry else set()

    def get_inlinks(self, relative_path: str) -> list[str]:
        """Return paths of notes that link TO relative_path (by stem)."""
        self._ensure_warm()
        target_stem = Path(relative_path).stem
        with self._lock:
            return [
                n.path for n in self._notes.values()
                if n.path != relative_path and target_stem in n.outlinks
            ]

    def all_tags(self) -> dict[str, int]:
        """Return {tag: count} across the entire vault."""
        self._ensure_warm()
        counts: dict[str, int] = {}
        with self._lock:
            for entry in self._notes.values():
                for tag in entry.tags:
                    counts[tag] = counts.get(tag, 0) + 1
        return counts

    def dir_counts(self) -> dict[str, int]:
        """Return {top_dir: note_count}."""
        self._ensure_warm()
        counts: dict[str, int] = {}
        with self._lock:
            for entry in self._notes.values():
                parts = Path(entry.path).parts
                top = parts[0] if len(parts) > 1 else "(root)"
                counts[top] = counts.get(top, 0) + 1
        return counts

    # -- Internal --

    def _read_note(self, md_file: Path, rel: str) -> CachedNote | None:
        """Read and parse a single .md file. Returns None on error."""
        try:
            content = md_file.read_text()
            mtime = md_file.stat().st_mtime
        except OSError:
            return None

        meta = _parse_frontmatter(content)
        title = meta.get("title", "") or md_file.stem
        date = meta.get("date", "")
        tags = _extract_tags(meta, content)
        outlinks = set()
        for match in _WIKILINK_RE.finditer(content):
            outlinks.add(match.group(1).strip())

        return CachedNote(
            path=rel,
            title=title,
            date=date,
            tags=tags,
            outlinks=outlinks,
            stem=md_file.stem,
            mtime=mtime,
        )


# -- Standalone parsing helpers (avoid coupling to ObsidianBackend) --

def _parse_frontmatter(content: str) -> dict:
    """Parse YAML frontmatter from note content."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    fm_block = content[3:end].strip()
    if not fm_block:
        return {}
    try:
        parsed = yaml.safe_load(fm_block)
        if isinstance(parsed, dict):
            result = {}
            for key, val in parsed.items():
                if isinstance(val, list):
                    result[key] = val
                elif val is None:
                    result[key] = ""
                else:
                    result[key] = str(val)
            return result
        return {}
    except yaml.YAMLError:
        return {}


def _extract_tags(meta: dict, content: str) -> list[str]:
    """Extract tags from YAML frontmatter or inline #tags."""
    yaml_tags = meta.get("tags")
    if isinstance(yaml_tags, list):
        return [str(t) for t in yaml_tags if t]
    if isinstance(yaml_tags, str) and yaml_tags:
        return yaml_tags.split()

    from alaya.vault import _parse_inline_tags
    body_start = content.find("\n---", 3)
    if body_start != -1:
        body = content[body_start + 4:].lstrip("\n")
    else:
        body = content
    return _parse_inline_tags(body)
