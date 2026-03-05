"""Pluggable vault backend: protocol, detection, and implementations."""

from alaya.backend.protocol import (
    VaultBackend,
    VaultConfig,
    NoteEntry,
    LinkEntry,
    TagEntry,
    LinkResolution,
)
from alaya.backend.config import detect_vault_type, load_vault_config, get_backend

__all__ = [
    "VaultBackend",
    "VaultConfig",
    "NoteEntry",
    "LinkEntry",
    "TagEntry",
    "LinkResolution",
    "detect_vault_type",
    "load_vault_config",
    "get_backend",
]
