"""ZkBackend: wraps the zk CLI into the VaultBackend protocol."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from alaya.backend.protocol import (
    LinkEntry,
    LinkResolution,
    NoteEntry,
    TagEntry,
    VaultConfig,
)
from alaya.vault import parse_note, render_frontmatter


class ZkBackend:
    """VaultBackend implementation backed by the zk CLI."""

    def __init__(self, config: VaultConfig) -> None:
        self.config = config

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
        from alaya.zk import run_zk, ZKError, _reject_flag

        args = [
            "list", "--format",
            "{{path}}\t{{title}}\t{{format-date created '%Y-%m-%d'}}\t{{tags}}",
            "--limit", str(limit),
        ]
        if tag:
            args += ["--tag", _reject_flag(tag, "tag")]
        if since:
            args += ["--modified-after", _reject_flag(since, "since")]
        if until:
            args += ["--modified-before", _reject_flag(until, "until")]
        if sort:
            args += ["--sort", _reject_flag(sort, "sort")]
        if directory:
            args += ["--", _reject_flag(directory, "directory")]

        try:
            raw = run_zk(args, self.config.root)
        except ZKError:
            return []

        if not raw:
            return []

        entries = []
        for line in raw.splitlines():
            parts = line.split("\t")
            path = parts[0] if len(parts) > 0 else ""
            title = parts[1] if len(parts) > 1 else ""
            date_str = parts[2] if len(parts) > 2 else ""
            tags_str = parts[3] if len(parts) > 3 else ""
            entries.append(NoteEntry(path=path, title=title, date=date_str, tags=tags_str))

        return entries

    def get_backlinks(self, relative_path: str) -> list[LinkEntry]:
        from alaya.zk import run_zk, ZKError

        try:
            raw = run_zk(
                ["list", "--link-to", relative_path, "--format", "{{path}}\t{{title}}"],
                self.config.root,
            )
        except ZKError:
            return []

        if not raw:
            return []

        entries = []
        for line in raw.splitlines():
            parts = line.split("\t")
            path = parts[0] if len(parts) > 0 else ""
            title = parts[1] if len(parts) > 1 else ""
            entries.append(LinkEntry(path=path, title=title or path))

        return entries

    def get_outlinks(self, relative_path: str) -> list[LinkEntry]:
        from alaya.zk import run_zk, ZKError

        try:
            raw = run_zk(
                ["list", "--linked-by", relative_path, "--format", "{{path}}\t{{title}}"],
                self.config.root,
            )
        except ZKError:
            return []

        if not raw:
            return []

        entries = []
        for line in raw.splitlines():
            parts = line.split("\t")
            path = parts[0] if len(parts) > 0 else ""
            title = parts[1] if len(parts) > 1 else ""
            entries.append(LinkEntry(path=path, title=title or path))

        return entries

    def list_tags(self) -> list[TagEntry]:
        from alaya.zk import run_zk, ZKError

        try:
            raw = run_zk(["tag", "list", "--format", "{{name}}\t{{note-count}}"], self.config.root)
        except ZKError:
            return []

        if not raw:
            return []

        entries = []
        for line in raw.splitlines():
            parts = line.split("\t")
            name = parts[0] if len(parts) > 0 else ""
            count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            entries.append(TagEntry(name=name, count=count))

        return entries

    def keyword_search(
        self,
        query: str,
        directory: str | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
    ) -> list[NoteEntry]:
        from alaya.zk import run_zk, ZKError, _reject_flag

        args = [
            "list",
            "--match", query,
            "--format", "{{path}}\t{{title}}\t{{format-date created '%Y-%m-%d'}}",
            "--limit", str(limit),
        ]
        if directory:
            args += ["--", _reject_flag(directory, "directory")]
        if tags:
            for tag in tags:
                args += ["--tag", _reject_flag(tag, "tag")]
        if since:
            args += ["--modified-after", _reject_flag(since, "since")]

        try:
            raw = run_zk(args, self.config.root)
        except ZKError:
            return []

        if not raw:
            return []

        entries = []
        for line in raw.splitlines():
            parts = line.split("\t")
            path = parts[0] if len(parts) > 0 else ""
            title = parts[1] if len(parts) > 1 else ""
            date_str = parts[2] if len(parts) > 2 else ""
            entries.append(NoteEntry(path=path, title=title, date=date_str))

        return entries

    def resolve_wikilink(self, link_text: str) -> Path | None:
        """Resolve a title-based wikilink to a file path."""
        from alaya.vault import iter_vault_md

        for md_file in iter_vault_md(self.config.root):
            try:
                content = md_file.read_text()
            except OSError:
                continue
            note = parse_note(content)
            title = note.title or md_file.stem
            if title == link_text:
                return md_file
        return None

    def parse_frontmatter(self, content: str) -> dict:
        note = parse_note(content)
        meta = {"title": note.title, "date": note.date}
        if note.tags:
            meta["tags"] = " ".join(f"#{t}" for t in note.tags)
        meta.update(note.extra)
        return meta

    def render_frontmatter(self, meta: dict) -> str:
        return render_frontmatter(meta)

    def note_link_key(self, path: Path, content: str) -> str:
        """Return the frontmatter title (zk uses title-based wikilinks)."""
        note = parse_note(content)
        return note.title or path.stem

    def check_available(self) -> None:
        """Verify the zk CLI is installed."""
        try:
            subprocess.run(
                ["zk", "--version"], capture_output=True, text=True, timeout=5
            )
        except FileNotFoundError:
            raise RuntimeError(
                "zk CLI not found. Install from: https://github.com/zk-org/zk"
            )
