"""VaultBackend protocol and shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol


class LinkResolution(Enum):
    """How wikilinks are resolved to note files."""
    TITLE = "title"        # zk style: [[frontmatter title]]
    FILENAME = "filename"  # Obsidian style: [[filename-stem]]


@dataclass
class VaultConfig:
    """Vault-wide configuration derived from detection + optional alaya.toml."""
    root: Path
    vault_type: str  # "zk" | "obsidian"
    data_dir_name: str  # ".zk" or ".obsidian"
    link_resolution: LinkResolution

    # Directory mapping: intent -> directory name
    directory_map: dict[str, str] = field(default_factory=lambda: {
        "person": "people",
        "idea": "ideas",
        "project": "projects",
        "learning": "learning",
        "resource": "resources",
        "daily": "daily",
    })

    daily_dir: str = "daily"
    people_dir: str = "people"
    archives_dir: str = "archives"
    default_capture_dir: str = "ideas"
    default_external_dir: str = "projects"

    # Directories to skip during full-vault scans
    skip_dirs: frozenset[str] = frozenset({".zk", ".obsidian", ".git", ".venv", "__pycache__", ".trash"})

    @property
    def data_dir(self) -> Path:
        return self.root / self.data_dir_name

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def index_state_path(self) -> Path:
        return self.data_dir / "index_state.json"

    @property
    def audit_log_path(self) -> Path:
        return self.data_dir / "audit.jsonl"


@dataclass
class NoteEntry:
    """A note returned by list/search operations."""
    path: str
    title: str
    date: str = ""
    tags: str = ""


@dataclass
class LinkEntry:
    """A link (backlink or outlink) between notes."""
    path: str
    title: str


@dataclass
class TagEntry:
    """A tag with its note count."""
    name: str
    count: int


class VaultBackend(Protocol):
    """Protocol that all vault backends must implement."""
    config: VaultConfig

    def list_notes(
        self,
        directory: str | None = None,
        tag: str | None = None,
        limit: int = 50,
        since: str | None = None,
        until: str | None = None,
        sort: str | None = None,
    ) -> list[NoteEntry]: ...

    def get_backlinks(self, relative_path: str) -> list[LinkEntry]: ...

    def get_outlinks(self, relative_path: str) -> list[LinkEntry]: ...

    def list_tags(self) -> list[TagEntry]: ...

    def keyword_search(
        self,
        query: str,
        directory: str | None = None,
        tags: list[str] | None = None,
        since: str | None = None,
        limit: int = 20,
    ) -> list[NoteEntry]: ...

    def resolve_wikilink(self, link_text: str) -> Path | None: ...

    def parse_frontmatter(self, content: str) -> dict: ...

    def render_frontmatter(self, meta: dict) -> str: ...

    def note_link_key(self, path: Path, content: str) -> str:
        """Return the wikilink key for a note (title for zk, filename stem for Obsidian)."""
        ...

    def check_available(self) -> None:
        """Raise if the backend's prerequisites are not met (e.g. zk binary missing)."""
        ...
