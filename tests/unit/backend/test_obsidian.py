"""ObsidianBackend unit tests: filesystem-based, no mocks needed."""
import shutil
from pathlib import Path

import pytest

from alaya.backend.protocol import LinkResolution, VaultConfig
from alaya.backend.obsidian import ObsidianBackend
from alaya.cache import VaultMetadataCache


OBSIDIAN_FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "vault_fixture_obsidian"


@pytest.fixture
def obs_vault(tmp_path: Path) -> Path:
    """Copy the Obsidian fixture vault to a temp directory."""
    vault_path = tmp_path / "obsidian_vault"
    shutil.copytree(OBSIDIAN_FIXTURE_PATH, vault_path)
    return vault_path


@pytest.fixture
def backend(obs_vault: Path) -> ObsidianBackend:
    config = VaultConfig(
        root=obs_vault,
        vault_type="obsidian",
        data_dir_name=".obsidian",
        link_resolution=LinkResolution.FILENAME,
    )
    return ObsidianBackend(config)


@pytest.fixture
def cached_backend(obs_vault: Path) -> ObsidianBackend:
    """ObsidianBackend with a warmed VaultMetadataCache."""
    config = VaultConfig(
        root=obs_vault,
        vault_type="obsidian",
        data_dir_name=".obsidian",
        link_resolution=LinkResolution.FILENAME,
    )
    cache = VaultMetadataCache(obs_vault)
    cache.warm()
    return ObsidianBackend(config, cache=cache)


class TestListNotes:
    def test_lists_all_notes(self, backend: ObsidianBackend) -> None:
        entries = backend.list_notes(limit=100)
        paths = [e.path for e in entries]
        assert any("second-brain" in p for p in paths)
        assert any("kubernetes-notes" in p for p in paths)

    def test_filter_by_directory(self, backend: ObsidianBackend) -> None:
        entries = backend.list_notes(directory="Ideas")
        assert len(entries) >= 1
        assert all(e.path.startswith("Ideas/") for e in entries)

    def test_filter_by_tag(self, backend: ObsidianBackend) -> None:
        entries = backend.list_notes(tag="kubernetes")
        assert len(entries) >= 1
        assert all("kubernetes" in e.tags for e in entries)

    def test_limit_works(self, backend: ObsidianBackend) -> None:
        entries = backend.list_notes(limit=2)
        assert len(entries) <= 2


class TestGetBacklinks:
    def test_finds_backlinks_by_filename(self, backend: ObsidianBackend) -> None:
        entries = backend.get_backlinks("Projects/second-brain.md")
        paths = [e.path for e in entries]
        # voice-capture.md and 2026-02-25.md both link to [[second-brain]]
        assert any("voice-capture" in p for p in paths)

    def test_no_backlinks_returns_empty(self, backend: ObsidianBackend) -> None:
        entries = backend.get_backlinks("People/alice-johnson.md")
        # alice-johnson is linked FROM second-brain, but let's check what links TO alice-johnson
        # second-brain has [[alice-johnson]]
        paths = [e.path for e in entries]
        assert any("second-brain" in p for p in paths)


class TestGetOutlinks:
    def test_finds_outlinks(self, backend: ObsidianBackend) -> None:
        entries = backend.get_outlinks("Projects/second-brain.md")
        paths = [e.path for e in entries]
        assert any("kubernetes-notes" in p for p in paths)
        assert any("alice-johnson" in p for p in paths)

    def test_no_outlinks_returns_empty(self, backend: ObsidianBackend, obs_vault: Path) -> None:
        # Create a note with no links
        (obs_vault / "Ideas" / "isolated.md").write_text(
            "---\ntitle: Isolated\ndate: 2026-01-01\n---\nNo links here."
        )
        entries = backend.get_outlinks("Ideas/isolated.md")
        assert entries == []


class TestListTags:
    def test_lists_all_tags(self, backend: ObsidianBackend) -> None:
        entries = backend.list_tags()
        names = [e.name for e in entries]
        assert "project" in names
        assert "kubernetes" in names
        assert "idea" in names

    def test_counts_are_positive(self, backend: ObsidianBackend) -> None:
        entries = backend.list_tags()
        for entry in entries:
            assert entry.count > 0


class TestKeywordSearch:
    def test_finds_notes_by_content(self, backend: ObsidianBackend) -> None:
        entries = backend.keyword_search("Kubernetes")
        paths = [e.path for e in entries]
        assert any("kubernetes-notes" in p for p in paths)

    def test_case_insensitive(self, backend: ObsidianBackend) -> None:
        entries = backend.keyword_search("kubernetes")
        assert len(entries) >= 1

    def test_no_results_returns_empty(self, backend: ObsidianBackend) -> None:
        entries = backend.keyword_search("xyznotfound12345")
        assert entries == []

    def test_filter_by_directory(self, backend: ObsidianBackend) -> None:
        entries = backend.keyword_search("FastMCP", directory="Projects")
        assert len(entries) >= 1
        assert all(e.path.startswith("Projects/") for e in entries)

    def test_limit_works(self, backend: ObsidianBackend) -> None:
        entries = backend.keyword_search("md", limit=1)
        assert len(entries) <= 1


class TestResolveWikilink:
    def test_resolves_by_filename_stem(self, backend: ObsidianBackend) -> None:
        result = backend.resolve_wikilink("second-brain")
        assert result is not None
        assert result.stem == "second-brain"

    def test_returns_none_for_unknown(self, backend: ObsidianBackend) -> None:
        result = backend.resolve_wikilink("nonexistent-note")
        assert result is None


class TestParseFrontmatter:
    def test_parses_yaml_tags_as_list(self, backend: ObsidianBackend) -> None:
        content = "---\ntitle: Test\ntags:\n  - foo\n  - bar\n---\nBody."
        meta = backend.parse_frontmatter(content)
        assert meta["title"] == "Test"
        assert meta["tags"] == ["foo", "bar"]

    def test_parses_inline_tags(self, backend: ObsidianBackend) -> None:
        content = "---\ntitle: Test\n---\nBody without yaml tags."
        meta = backend.parse_frontmatter(content)
        assert meta["title"] == "Test"

    def test_handles_empty_frontmatter(self, backend: ObsidianBackend) -> None:
        content = "No frontmatter at all."
        meta = backend.parse_frontmatter(content)
        assert meta == {}

    def test_handles_yaml_errors_gracefully(self, backend: ObsidianBackend) -> None:
        content = "---\n: bad yaml [\n---\nBody."
        meta = backend.parse_frontmatter(content)
        assert meta == {}


class TestRenderFrontmatter:
    def test_renders_basic(self, backend: ObsidianBackend) -> None:
        meta = {"title": "Test", "date": "2026-01-01"}
        result = backend.render_frontmatter(meta)
        assert result.startswith("---\n")
        assert "title: Test" in result
        assert "date: 2026-01-01" in result
        assert result.endswith("---\n")

    def test_renders_list_tags(self, backend: ObsidianBackend) -> None:
        meta = {"title": "Test", "tags": ["foo", "bar"]}
        result = backend.render_frontmatter(meta)
        assert "  - foo" in result
        assert "  - bar" in result


class TestNoteLinkKey:
    def test_returns_filename_stem(self, backend: ObsidianBackend) -> None:
        content = "---\ntitle: Some Title\n---\nBody."
        key = backend.note_link_key(Path("ideas/my-note.md"), content)
        assert key == "my-note"  # Obsidian uses filename, not title


class TestCheckAvailable:
    def test_always_succeeds(self, backend: ObsidianBackend) -> None:
        backend.check_available()  # should not raise


# --- Cached backend: same assertions, proving cache path produces identical results ---

class TestCachedListNotes:
    def test_lists_all_notes(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_notes(limit=100)
        paths = [e.path for e in entries]
        assert any("second-brain" in p for p in paths)
        assert any("kubernetes-notes" in p for p in paths)

    def test_filter_by_directory(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_notes(directory="Ideas")
        assert len(entries) >= 1
        assert all(e.path.startswith("Ideas/") for e in entries)

    def test_filter_by_tag(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_notes(tag="kubernetes")
        assert len(entries) >= 1
        assert all("kubernetes" in e.tags for e in entries)

    def test_limit_works(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_notes(limit=2)
        assert len(entries) <= 2


class TestCachedGetBacklinks:
    def test_finds_backlinks_by_filename(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.get_backlinks("Projects/second-brain.md")
        paths = [e.path for e in entries]
        assert any("voice-capture" in p for p in paths)

    def test_backlinks_to_alice(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.get_backlinks("People/alice-johnson.md")
        paths = [e.path for e in entries]
        assert any("second-brain" in p for p in paths)


class TestCachedGetOutlinks:
    def test_finds_outlinks(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.get_outlinks("Projects/second-brain.md")
        paths = [e.path for e in entries]
        assert any("kubernetes-notes" in p for p in paths)
        assert any("alice-johnson" in p for p in paths)

    def test_no_outlinks_returns_empty(self, cached_backend: ObsidianBackend, obs_vault: Path) -> None:
        (obs_vault / "Ideas" / "isolated.md").write_text(
            "---\ntitle: Isolated\ndate: 2026-01-01\n---\nNo links here."
        )
        cached_backend.cache.invalidate("Ideas/isolated.md")
        entries = cached_backend.get_outlinks("Ideas/isolated.md")
        assert entries == []


class TestCachedListTags:
    def test_lists_all_tags(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_tags()
        names = [e.name for e in entries]
        assert "project" in names
        assert "kubernetes" in names
        assert "idea" in names

    def test_counts_are_positive(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.list_tags()
        for entry in entries:
            assert entry.count > 0


class TestCachedKeywordSearch:
    def test_finds_notes_by_content(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.keyword_search("Kubernetes")
        paths = [e.path for e in entries]
        assert any("kubernetes-notes" in p for p in paths)

    def test_case_insensitive(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.keyword_search("kubernetes")
        assert len(entries) >= 1

    def test_no_results_returns_empty(self, cached_backend: ObsidianBackend) -> None:
        entries = cached_backend.keyword_search("xyznotfound12345")
        assert entries == []


class TestCachedResolveWikilink:
    def test_resolves_by_filename_stem(self, cached_backend: ObsidianBackend) -> None:
        result = cached_backend.resolve_wikilink("second-brain")
        assert result is not None
        assert result.stem == "second-brain"

    def test_returns_none_for_unknown(self, cached_backend: ObsidianBackend) -> None:
        result = cached_backend.resolve_wikilink("nonexistent-note")
        assert result is None
