"""External provider registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


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


_PROVIDER_FACTORIES: dict[str, Callable[[], Provider]] = {}
# url_pattern -> provider name; checked as substring of lowercased source
_URL_PATTERNS: dict[str, str] = {}


def register_provider(name: str, factory: Callable[[], Provider], url_pattern: str) -> None:
    """Register a provider factory and its URL pattern for auto-detection."""
    _PROVIDER_FACTORIES[name] = factory
    _URL_PATTERNS[url_pattern] = name


def detect_provider(source: str) -> str | None:
    """Detect provider name from URL or shorthand like 'gitlab:open'."""
    lower = source.lower()
    for pattern, name in _URL_PATTERNS.items():
        if pattern in lower or lower.startswith(f"{name}:"):
            return name
    return None


def get_provider(name: str) -> Provider:
    """Return a provider instance by name. Raises ValueError if unknown."""
    factory = _PROVIDER_FACTORIES.get(name)
    if not factory:
        supported = sorted(_PROVIDER_FACTORIES)
        raise ValueError(f"Unsupported provider: {name!r}. Supported: {supported}")
    return factory()


# Register built-in providers. Imports are deferred so the registry module
# itself has no heavy dependencies at import time.
def _register_builtins() -> None:
    from alaya.tools.providers.gitlab import GitLabProvider
    from alaya.tools.providers.github import GitHubProvider
    register_provider("gitlab", GitLabProvider, "gitlab.com")
    register_provider("github", GitHubProvider, "github.com")


_register_builtins()
