"""ObsidianBackend: pure-Python vault backend for Obsidian vaults."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from alaya.backend.protocol import (
    LinkEntry,
    NoteEntry,
    TagEntry,
    VaultConfig,
)
from alaya.vault import iter_vault_md

_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


class ObsidianBackend:
    """VaultBackend implementation for Obsidian vaults (pure Python, no CLI)."""

    def __init__(self, config: VaultConfig, cache=None) -> None:
        self.config = config
        self.cache = cache

    # -- Protocol methods --

    def list_notes(
        self,
        directory: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        since: str | None = None,
        until: str | None = None,
        sort: str | None = None,
    ) -> list[NoteEntry]:
        if self.cache:
            return self._list_notes_cached(directory, tag, limit, since, until, sort)

        entries: list[NoteEntry] = []

        for md_file in iter_vault_md(self.config.root):
            rel = str(md_file.relative_to(self.config.root))

            if directory and not rel.startswith(directory.rstrip("/") + "/"):
                continue

            try:
                content = md_file.read_text()
            except OSError:
                continue

            meta = self.parse_frontmatter(content)
            title = meta.get("title", "") or md_file.stem
            date_str = meta.get("date", "")
            file_tags = self._extract_tags(meta, content)
            tags_str = " ".join(f"#{t}" for t in file_tags)

            if tag and tag not in file_tags:
                continue

            if since and date_str < since:
                continue
            if until and date_str > until:
                continue

            mtime = ""
            try:
                mtime = md_file.stat().st_mtime
            except OSError:
                pass

            entries.append(NoteEntry(path=rel, title=title, date=date_str, tags=tags_str))

        # Sort
        if sort == "title":
            entries.sort(key=lambda e: e.title.lower())
        elif sort == "created":
            entries.sort(key=lambda e: e.date, reverse=True)
        else:
            # default: modification time (most recent first) — use path as proxy
            entries.sort(key=lambda e: e.path, reverse=True)

        return entries[:limit]

    def _list_notes_cached(self, directory, tag, limit, since, until, sort):
        entries: list[NoteEntry] = []
        for n in self.cache.iter_notes():
            if directory and not n.path.startswith(directory.rstrip("/") + "/"):
                continue
            if tag and tag not in n.tags:
                continue
            if since and n.date < since:
                continue
            if until and n.date > until:
                continue
            tags_str = " ".join(f"#{t}" for t in n.tags)
            entries.append(NoteEntry(path=n.path, title=n.title, date=n.date, tags=tags_str))

        if sort == "title":
            entries.sort(key=lambda e: e.title.lower())
        elif sort == "created":
            entries.sort(key=lambda e: e.date, reverse=True)
        else:
            entries.sort(key=lambda e: e.path, reverse=True)
        return entries[:limit]

    def get_backlinks(self, relative_path: str) -> list[LinkEntry]:
        """Find notes that link to relative_path using [[filename]] wikilinks."""
        if self.cache:
            entries = []
            for src_path in self.cache.get_inlinks(relative_path):
                meta = self.cache.get_meta(src_path)
                if meta:
                    entries.append(LinkEntry(path=src_path, title=meta.title))
            return entries

        target_stem = Path(relative_path).stem
        entries: list[LinkEntry] = []

        for md_file in iter_vault_md(self.config.root):
            rel = str(md_file.relative_to(self.config.root))
            if rel == relative_path:
                continue
            try:
                content = md_file.read_text()
            except OSError:
                continue

            for match in _WIKILINK_RE.finditer(content):
                link_text = match.group(1).strip()
                if link_text == target_stem:
                    meta = self.parse_frontmatter(content)
                    title = meta.get("title", "") or md_file.stem
                    entries.append(LinkEntry(path=rel, title=title))
                    break

        return entries

    def get_outlinks(self, relative_path: str) -> list[LinkEntry]:
        """Find notes linked from relative_path."""
        if self.cache:
            entries = []
            for link_text in self.cache.get_outlinks(relative_path):
                target_path = self.cache.stem_to_path(link_text)
                if target_path:
                    meta = self.cache.get_meta(target_path)
                    if meta:
                        entries.append(LinkEntry(path=target_path, title=meta.title))
            return entries

        full_path = self.config.root / relative_path
        if not full_path.exists():
            return []

        try:
            content = full_path.read_text()
        except OSError:
            return []

        # Build stem -> (path, title) lookup
        stem_to_note: dict[str, tuple[str, str]] = {}
        for md_file in iter_vault_md(self.config.root):
            rel = str(md_file.relative_to(self.config.root))
            try:
                c = md_file.read_text()
            except OSError:
                continue
            meta = self.parse_frontmatter(c)
            title = meta.get("title", "") or md_file.stem
            stem_to_note[md_file.stem] = (rel, title)

        entries: list[LinkEntry] = []
        seen = set()
        for match in _WIKILINK_RE.finditer(content):
            link_text = match.group(1).strip()
            if link_text in seen:
                continue
            seen.add(link_text)
            if link_text in stem_to_note:
                path, title = stem_to_note[link_text]
                entries.append(LinkEntry(path=path, title=title))

        return entries

    def list_tags(self) -> list[TagEntry]:
        """Scan all notes for tags (YAML frontmatter + inline)."""
        if self.cache:
            tag_counts = self.cache.all_tags()
            return [TagEntry(name=name, count=count) for name, count in sorted(tag_counts.items())]

        tag_counts: dict[str, int] = {}

        for md_file in iter_vault_md(self.config.root):
            try:
                content = md_file.read_text()
            except OSError:
                continue

            meta = self.parse_frontmatter(content)
            tags = self._extract_tags(meta, content)
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        entries = [TagEntry(name=name, count=count) for name, count in sorted(tag_counts.items())]
        return entries

    def keyword_search(
        self,
        query: str,
        directory: str | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
    ) -> list[NoteEntry]:
        """Simple substring search across all .md files."""
        if self.cache:
            return self._keyword_search_cached(query, directory, tags, since, limit)

        query_lower = query.lower()
        entries: list[NoteEntry] = []

        for md_file in iter_vault_md(self.config.root):
            rel = str(md_file.relative_to(self.config.root))

            if directory and not rel.startswith(directory.rstrip("/") + "/"):
                continue

            try:
                content = md_file.read_text()
            except OSError:
                continue

            if query_lower not in content.lower():
                continue

            meta = self.parse_frontmatter(content)
            title = meta.get("title", "") or md_file.stem
            date_str = meta.get("date", "")
            file_tags = self._extract_tags(meta, content)

            if tags and not any(t in file_tags for t in tags):
                continue
            if since and date_str < since:
                continue

            entries.append(NoteEntry(path=rel, title=title, date=date_str))

            if len(entries) >= limit:
                break

        return entries

    def _keyword_search_cached(self, query, directory, tags, since, limit):
        """Keyword search using cache for metadata, still reads content for matching."""
        query_lower = query.lower()
        entries: list[NoteEntry] = []

        for n in self.cache.iter_notes():
            if directory and not n.path.startswith(directory.rstrip("/") + "/"):
                continue
            if tags and not any(t in n.tags for t in tags):
                continue
            if since and n.date < since:
                continue

            try:
                content = (self.config.root / n.path).read_text()
            except OSError:
                continue

            if query_lower not in content.lower():
                continue

            entries.append(NoteEntry(path=n.path, title=n.title, date=n.date))
            if len(entries) >= limit:
                break

        return entries

    def resolve_wikilink(self, link_text: str) -> Path | None:
        """Resolve a filename-based wikilink to a file path (shortest path wins)."""
        if self.cache:
            rel = self.cache.stem_to_path(link_text)
            return (self.config.root / rel) if rel else None

        candidates: list[Path] = []

        for md_file in iter_vault_md(self.config.root):
            if md_file.stem == link_text:
                candidates.append(md_file)

        if not candidates:
            return None

        # Obsidian uses shortest-path resolution when multiple files share a stem
        candidates.sort(key=lambda p: len(str(p.relative_to(self.config.root))))
        return candidates[0]

    def parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter using yaml.safe_load."""
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
                # Normalize values to strings for consistency
                result = {}
                for key, val in parsed.items():
                    if isinstance(val, list):
                        result[key] = val  # preserve lists (e.g. tags)
                    elif val is None:
                        result[key] = ""
                    else:
                        result[key] = str(val)
                return result
            return {}
        except yaml.YAMLError:
            return {}

    def render_frontmatter(self, meta: dict) -> str:
        """Render a dict as YAML frontmatter."""
        lines = ["---"]
        for key, val in meta.items():
            if isinstance(val, list):
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {item}")
            elif val:
                lines.append(f"{key}: {val}")
            else:
                lines.append(f"{key}:")
        lines.append("---\n")
        return "\n".join(lines)

    def note_link_key(self, path: Path, content: str) -> str:
        """Return the filename stem (Obsidian uses filename-based wikilinks)."""
        return path.stem

    def check_available(self) -> None:
        """Obsidian backend has no external dependencies."""
        pass

    # -- Internal helpers --

    def _extract_tags(self, meta: dict, content: str) -> list[str]:
        """Extract tags from YAML frontmatter tags list, falling back to inline #tags."""
        yaml_tags = meta.get("tags")
        if isinstance(yaml_tags, list):
            return [str(t) for t in yaml_tags if t]
        if isinstance(yaml_tags, str) and yaml_tags:
            return yaml_tags.split()

        # Fall back to inline #tag parsing (same as zk)
        from alaya.vault import _parse_inline_tags
        body_start = content.find("\n---", 3)
        if body_start != -1:
            body = content[body_start + 4:].lstrip("\n")
        else:
            body = content
        return _parse_inline_tags(body)
