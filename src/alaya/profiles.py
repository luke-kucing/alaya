"""Tool profiles: register only the tools a role needs.

alaya exposes ~30 tools. For 27B-class local models the JSON schemas are a real
fraction of the context window, and the size of the decision surface measurably
hurts tool-call accuracy. A profile trims the exposed set at startup, so every
client gets the benefit rather than each having to filter for itself.

Profile entries may be written with or without the ``_tool`` suffix that FastMCP
registration adds (see #150), so ``search_notes`` and ``search_notes_tool`` both
match the same tool.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ALL = "*"
DEFAULT_PROFILE = "librarian"

BUILTIN_PROFILES: dict[str, list[str] | str] = {
    # Everything. The default, so existing clients see no change.
    "librarian": ALL,
    # A harness orchestrator: memory, search, and capture. No structural edits.
    "orchestrator": [
        "memory_recall",
        "memory_checkpoint",
        "memory_resume",
        "search_notes",
        "get_note",
        "smart_capture",
        "append_to_note",
        "get_todos",
    ],
    # Evaluators and reviewers: read the vault, never change it.
    "readonly": [
        "search_notes",
        "get_note",
        "list_notes",
        "get_backlinks",
        "get_links",
        "get_tags",
        "vault_stats",
        "vault_health",
        "memory_recall",
    ],
}


class ProfileError(Exception):
    """Raised when a profile is unknown or names a tool that does not exist."""


def _canonical(name: str) -> str:
    """Strip the registration suffix so profiles can be written either way."""
    return name.removesuffix("_tool")


def get_profile_name(override: str | None = None) -> str:
    """Resolve the active profile name.

    Precedence: explicit override (CLI) > ALAYA_TOOL_PROFILE > default.
    """
    return override or os.environ.get("ALAYA_TOOL_PROFILE") or DEFAULT_PROFILE


def load_profiles(vault_root: Path | None = None) -> dict[str, list[str] | str]:
    """Return built-in profiles merged with any defined in alaya.toml.

    User definitions override built-ins of the same name.
    """
    profiles = dict(BUILTIN_PROFILES)
    if vault_root is None:
        return profiles

    from alaya.backend.config import _load_toml

    try:
        toml_config = _load_toml(vault_root) or {}
    except Exception as e:
        logger.warning("Could not read alaya.toml for profiles: %s", e)
        return profiles

    for name, entries in (toml_config.get("profiles") or {}).items():
        if entries == ALL or isinstance(entries, list):
            profiles[name] = entries
        else:
            raise ProfileError(
                f"Profile {name!r} in alaya.toml must be a list of tool names or \"*\", "
                f"got {type(entries).__name__}"
            )
    return profiles


def resolve_profile(
    profile_name: str,
    registered: set[str],
    vault_root: Path | None = None,
) -> set[str] | None:
    """Return the set of registered tool names to keep, or None to keep all.

    Raises ProfileError if the profile is unknown or names a tool that is not
    registered — a silently empty tool list is far worse than a startup failure.
    """
    profiles = load_profiles(vault_root)

    if profile_name not in profiles:
        known = ", ".join(sorted(profiles))
        raise ProfileError(f"Unknown tool profile {profile_name!r}. Known profiles: {known}")

    entries = profiles[profile_name]
    if entries == ALL:
        return None

    by_canonical = {_canonical(name): name for name in registered}
    keep: set[str] = set()
    unknown: list[str] = []
    for entry in entries:
        actual = by_canonical.get(_canonical(entry))
        if actual is None:
            unknown.append(entry)
        else:
            keep.add(actual)

    if unknown:
        raise ProfileError(
            f"Profile {profile_name!r} names tools that are not registered: "
            f"{', '.join(sorted(unknown))}"
        )
    return keep


async def apply_profile(mcp, profile_name: str, vault_root: Path | None = None) -> set[str]:
    """Remove every registered tool outside *profile_name*. Returns what remains."""
    registered = {t.name for t in await mcp.list_tools()}
    keep = resolve_profile(profile_name, registered, vault_root)

    if keep is None:
        logger.info("Tool profile %r: all %d tools exposed", profile_name, len(registered))
        return registered

    remove = getattr(getattr(mcp, "local_provider", None), "remove_tool", None) or mcp.remove_tool
    for name in sorted(registered - keep):
        remove(name)

    logger.info(
        "Tool profile %r: exposing %d of %d tools", profile_name, len(keep), len(registered)
    )
    return keep
