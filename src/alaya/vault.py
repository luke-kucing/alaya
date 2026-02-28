"""Vault path utilities shared across tools."""
from pathlib import Path


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
