"""Unit tests for tool profiles."""
from pathlib import Path

import pytest
from fastmcp import FastMCP

from alaya import profiles
from alaya.profiles import (
    ALL,
    BUILTIN_PROFILES,
    ProfileError,
    _canonical,
    apply_profile,
    get_profile_name,
    load_profiles,
    resolve_profile,
)

REGISTERED = {
    "search_notes_tool",
    "get_note_tool",
    "list_notes_tool",
    "get_backlinks_tool",
    "get_links_tool",
    "get_tags_tool",
    "vault_stats_tool",
    "create_note_tool",
    "delete_note_tool",
    "memory_recall_tool",
    "vault_health",
}


class TestCanonical:
    def test_strips_tool_suffix(self) -> None:
        assert _canonical("search_notes_tool") == "search_notes"

    def test_leaves_unsuffixed_names_alone(self) -> None:
        assert _canonical("vault_health") == "vault_health"

    def test_only_strips_a_trailing_suffix(self) -> None:
        assert _canonical("tool_belt") == "tool_belt"


class TestGetProfileName:
    def test_defaults_to_librarian(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALAYA_TOOL_PROFILE", raising=False)
        assert get_profile_name() == "librarian"

    def test_env_var_selects_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_TOOL_PROFILE", "readonly")
        assert get_profile_name() == "readonly"

    def test_cli_override_beats_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALAYA_TOOL_PROFILE", "readonly")
        assert get_profile_name("orchestrator") == "orchestrator"


class TestResolveProfile:
    def test_librarian_keeps_everything(self) -> None:
        assert resolve_profile("librarian", REGISTERED) is None

    def test_matches_names_written_without_suffix(self) -> None:
        keep = resolve_profile("readonly", REGISTERED)
        assert "search_notes_tool" in keep
        assert "get_note_tool" in keep

    def test_excludes_tools_outside_the_profile(self) -> None:
        keep = resolve_profile("readonly", REGISTERED)
        assert "delete_note_tool" not in keep
        assert "create_note_tool" not in keep

    def test_unknown_profile_raises_and_names_known_ones(self) -> None:
        with pytest.raises(ProfileError) as exc:
            resolve_profile("nope", REGISTERED)
        assert "nope" in str(exc.value)
        assert "librarian" in str(exc.value)

    def test_unknown_tool_in_profile_raises_with_the_bad_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(BUILTIN_PROFILES, "broken", ["search_notes", "no_such_tool"])
        with pytest.raises(ProfileError) as exc:
            resolve_profile("broken", REGISTERED)
        assert "no_such_tool" in str(exc.value)

    def test_suffixed_names_in_a_profile_also_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(BUILTIN_PROFILES, "suffixed", ["search_notes_tool"])
        assert resolve_profile("suffixed", REGISTERED) == {"search_notes_tool"}


class TestLoadProfiles:
    def test_builtins_present_without_a_toml(self, vault: Path) -> None:
        loaded = load_profiles(vault)
        assert set(BUILTIN_PROFILES) <= set(loaded)

    def test_toml_profile_is_merged(self, vault: Path) -> None:
        (vault / "alaya.toml").write_text(
            '[vault]\ntype = "zk"\n\n[profiles]\ncustom = ["get_note"]\n'
        )
        loaded = load_profiles(vault)
        assert loaded["custom"] == ["get_note"]

    def test_toml_overrides_a_builtin(self, vault: Path) -> None:
        (vault / "alaya.toml").write_text(
            '[vault]\ntype = "zk"\n\n[profiles]\nreadonly = ["get_note"]\n'
        )
        assert load_profiles(vault)["readonly"] == ["get_note"]

    def test_star_is_accepted_from_toml(self, vault: Path) -> None:
        (vault / "alaya.toml").write_text(
            '[vault]\ntype = "zk"\n\n[profiles]\neverything = "*"\n'
        )
        assert load_profiles(vault)["everything"] == ALL

    def test_malformed_profile_raises(self, vault: Path) -> None:
        (vault / "alaya.toml").write_text(
            '[vault]\ntype = "zk"\n\n[profiles]\nbad = 3\n'
        )
        with pytest.raises(ProfileError):
            load_profiles(vault)


class TestApplyProfile:
    @pytest.mark.asyncio
    async def test_removes_tools_outside_the_profile(self, vault: Path) -> None:
        from alaya.tools import memory, read, search, stats, write

        mcp = FastMCP(name="alaya-test")
        for mod in (read, search, write, stats, memory):
            mod._register(mcp, vault)

        @mcp.tool()
        def vault_health() -> str:
            """Stand-in for the health tool registered by the server."""
            return ""

        keep = await apply_profile(mcp, "readonly", vault)
        remaining = {t.name for t in await mcp.list_tools()}

        assert remaining == keep
        assert "search_notes_tool" in remaining
        assert "create_note_tool" not in remaining

    @pytest.mark.asyncio
    async def test_librarian_removes_nothing(self, vault: Path) -> None:
        from alaya.tools import read, write

        mcp = FastMCP(name="alaya-test")
        read._register(mcp, vault)
        write._register(mcp, vault)
        before = {t.name for t in await mcp.list_tools()}

        await apply_profile(mcp, "librarian", vault)
        assert {t.name for t in await mcp.list_tools()} == before

    @pytest.mark.asyncio
    async def test_unknown_profile_raises_before_removing_anything(self, vault: Path) -> None:
        from alaya.tools import read

        mcp = FastMCP(name="alaya-test")
        read._register(mcp, vault)
        before = {t.name for t in await mcp.list_tools()}

        with pytest.raises(ProfileError):
            await apply_profile(mcp, "nope", vault)
        assert {t.name for t in await mcp.list_tools()} == before


class TestBuiltinProfileContents:
    """The built-in profiles must name tools that actually exist."""

    @pytest.mark.asyncio
    async def test_every_builtin_resolves_against_the_real_tool_set(self, vault: Path) -> None:
        from alaya.tools import (
            capture, edit, enrich, external, graph, ingest, inbox,
            memory, read, search, stats, structure, tasks, write,
        )

        mcp = FastMCP(name="alaya-test")
        for mod in (read, search, structure, edit, graph, capture, external,
                    write, inbox, tasks, ingest, stats, enrich, memory):
            mod._register(mcp, vault)

        @mcp.tool()
        def vault_health() -> str:
            """Stand-in for the health tool registered by the server."""
            return ""

        registered = {t.name for t in await mcp.list_tools()}
        for name in BUILTIN_PROFILES:
            # Raises ProfileError if a profile names a tool that does not exist.
            resolve_profile(name, registered)

    def test_orchestrator_is_a_small_surface(self) -> None:
        assert len(BUILTIN_PROFILES["orchestrator"]) <= 10

    def test_readonly_has_no_write_tools(self) -> None:
        forbidden = ("create", "delete", "move", "rename", "append", "replace", "capture")
        for name in BUILTIN_PROFILES["readonly"]:
            assert not any(f in name for f in forbidden), name
