"""External provider registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class ExternalItem:
    url: str
    title: str
    body: str
    labels: list[str]
    state: str
    provider: str


class Provider(Protocol):
    def fetch_item(self, url: str) -> ExternalItem: ...
    def fetch_items(self, query: str) -> list[ExternalItem]: ...
    def create_item(self, title: str, body: str, labels: list[str]) -> str: ...  # returns URL


def detect_provider(source: str) -> str | None:
    """Detect provider name from URL or shorthand like 'gitlab:open'."""
    lower = source.lower()
    if "gitlab.com" in lower or lower.startswith("gitlab:"):
        return "gitlab"
    if "github.com" in lower or lower.startswith("github:"):
        return "github"
    return None


def get_provider(name: str) -> Provider:
    """Return a provider instance by name. Raises ValueError if unknown."""
    if name == "gitlab":
        from alaya.tools.providers.gitlab import GitLabProvider
        return GitLabProvider()
    if name == "github":
        from alaya.tools.providers.github import GitHubProvider
        return GitHubProvider()
    raise ValueError(f"Unsupported provider: {name!r}. Supported: gitlab, github")
