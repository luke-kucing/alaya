"""VaultMetadataCache unit tests: filesystem-based using the Obsidian fixture."""
import shutil
from pathlib import Path

import pytest

from alaya.cache import VaultMetadataCache


OBSIDIAN_FIXTURE_PATH = Path(__file__).parent.parent.parent / "vault_fixture_obsidian"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Copy the Obsidian fixture vault to a temp directory."""
    vault_path = tmp_path / "vault"
    shutil.copytree(OBSIDIAN_FIXTURE_PATH, vault_path)
    return vault_path


@pytest.fixture
def cache(vault: Path) -> VaultMetadataCache:
    c = VaultMetadataCache(vault)
    c.warm()
    return c


class TestWarm:
    def test_finds_all_notes(self, cache: VaultMetadataCache) -> None:
        notes = cache.iter_notes()
        paths = {n.path for n in notes}
        assert len(paths) == 5
        assert any("second-brain" in p for p in paths)
        assert any("kubernetes-notes" in p for p in paths)
        assert any("alice-johnson" in p for p in paths)

    def test_lazy_warm_on_first_access(self, vault: Path) -> None:
        c = VaultMetadataCache(vault)
        assert c._warmed is False
        notes = c.iter_notes()
        assert c._warmed is True
        assert len(notes) == 5

    def test_skips_dotdirs(self, vault: Path) -> None:
        # Create a file in .obsidian that should be skipped
        (vault / ".obsidian" / "test.md").write_text("---\ntitle: Hidden\n---\nBody.")
        c = VaultMetadataCache(vault)
        c.warm()
        paths = {n.path for n in c.iter_notes()}
        assert not any(".obsidian" in p for p in paths)


class TestTitleToPath:
    def test_finds_by_title(self, cache: VaultMetadataCache) -> None:
        path = cache.title_to_path("Second Brain")
        assert path is not None
        assert "second-brain" in path

    def test_case_insensitive(self, cache: VaultMetadataCache) -> None:
        path = cache.title_to_path("second brain")
        assert path is not None

    def test_returns_none_for_unknown(self, cache: VaultMetadataCache) -> None:
        assert cache.title_to_path("nonexistent") is None


class TestStemToPath:
    def test_finds_by_stem(self, cache: VaultMetadataCache) -> None:
        path = cache.stem_to_path("second-brain")
        assert path is not None
        assert "second-brain" in path

    def test_returns_none_for_unknown(self, cache: VaultMetadataCache) -> None:
        assert cache.stem_to_path("nonexistent") is None


class TestOutlinks:
    def test_returns_outlinks(self, cache: VaultMetadataCache) -> None:
        # second-brain.md links to [[kubernetes-notes]] and [[alice-johnson]]
        path = cache.stem_to_path("second-brain")
        outlinks = cache.get_outlinks(path)
        assert "kubernetes-notes" in outlinks
        assert "alice-johnson" in outlinks

    def test_no_outlinks(self, cache: VaultMetadataCache, vault: Path) -> None:
        (vault / "isolated.md").write_text("---\ntitle: Isolated\n---\nNo links.")
        cache.invalidate("isolated.md")
        assert cache.get_outlinks("isolated.md") == set()


class TestInlinks:
    def test_finds_inlinks(self, cache: VaultMetadataCache) -> None:
        # second-brain is linked from voice-capture.md and 2026-02-25.md
        path = cache.stem_to_path("second-brain")
        inlinks = cache.get_inlinks(path)
        assert any("voice-capture" in p for p in inlinks)

    def test_no_inlinks(self, cache: VaultMetadataCache, vault: Path) -> None:
        (vault / "orphan.md").write_text("---\ntitle: Orphan\n---\nNobody links here.")
        cache.invalidate("orphan.md")
        assert cache.get_inlinks("orphan.md") == []


class TestAllTags:
    def test_returns_tag_counts(self, cache: VaultMetadataCache) -> None:
        tags = cache.all_tags()
        assert "project" in tags
        assert "kubernetes" in tags
        assert all(c > 0 for c in tags.values())


class TestDirCounts:
    def test_returns_dir_counts(self, cache: VaultMetadataCache) -> None:
        counts = cache.dir_counts()
        assert "Projects" in counts
        assert counts["Projects"] == 2


class TestInvalidate:
    def test_updates_existing_note(self, cache: VaultMetadataCache, vault: Path) -> None:
        # Modify the title of second-brain.md
        sb_path = None
        for n in cache.iter_notes():
            if "second-brain" in n.path:
                sb_path = n.path
                break
        assert sb_path is not None

        full = vault / sb_path
        full.write_text("---\ntitle: Renamed Brain\ndate: 2026-02-23\ntags:\n  - project\n---\nBody.")
        cache.invalidate(sb_path)

        # Old title should no longer resolve
        assert cache.title_to_path("Second Brain") is None
        # New title should resolve
        assert cache.title_to_path("Renamed Brain") == sb_path

    def test_adds_new_note(self, cache: VaultMetadataCache, vault: Path) -> None:
        (vault / "new-note.md").write_text("---\ntitle: Brand New\ndate: 2026-03-01\n---\nContent.")
        cache.invalidate("new-note.md")

        assert cache.title_to_path("Brand New") == "new-note.md"
        assert cache.stem_to_path("new-note") == "new-note.md"
        meta = cache.get_meta("new-note.md")
        assert meta is not None
        assert meta.title == "Brand New"


class TestRemove:
    def test_removes_note(self, cache: VaultMetadataCache) -> None:
        path = cache.stem_to_path("second-brain")
        assert path is not None
        cache.remove(path)
        assert cache.stem_to_path("second-brain") is None
        assert cache.title_to_path("Second Brain") is None
        assert cache.get_meta(path) is None

    def test_remove_nonexistent_is_noop(self, cache: VaultMetadataCache) -> None:
        cache.remove("nonexistent.md")  # should not raise
