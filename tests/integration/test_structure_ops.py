"""Integration tests for structure operations: move, rename, delete, find_references.

These tests operate on a per-test copy of the vault (tmp_path), so they can
safely mutate the filesystem.
"""
import pytest
import shutil
from pathlib import Path

from alaya.tools.structure import move_note, rename_note, delete_note, find_references
from alaya.tools.write import append_to_note


pytestmark = pytest.mark.integration


@pytest.fixture
def mut_vault(large_vault: Path, tmp_path: Path) -> Path:
    """Per-test mutable copy of the large vault."""
    dest = tmp_path / "vault"
    shutil.copytree(large_vault, dest)
    return dest


class TestMoveNote:
    def test_file_appears_in_new_location(self, mut_vault: Path) -> None:
        new_path = move_note("ideas/voice-capture.md", "resources", mut_vault)
        assert (mut_vault / new_path).exists()
        assert "resources" in new_path

    def test_original_file_removed(self, mut_vault: Path) -> None:
        move_note("ideas/voice-capture.md", "resources", mut_vault)
        assert not (mut_vault / "ideas" / "voice-capture.md").exists()

    def test_returns_new_relative_path(self, mut_vault: Path) -> None:
        new_path = move_note("ideas/voice-capture.md", "resources", mut_vault)
        assert isinstance(new_path, str)
        assert not new_path.startswith("/")

    def test_missing_note_raises(self, mut_vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            move_note("ideas/ghost.md", "resources", mut_vault)

    def test_invalid_destination_raises(self, mut_vault: Path) -> None:
        with pytest.raises(ValueError):
            move_note("ideas/voice-capture.md", "../../etc", mut_vault)


class TestRenameNote:
    def test_new_file_exists(self, mut_vault: Path) -> None:
        new_path = rename_note("resources/kubernetes-notes.md", "k8s-reference", mut_vault)
        assert (mut_vault / new_path).exists()

    def test_old_file_removed(self, mut_vault: Path) -> None:
        rename_note("resources/kubernetes-notes.md", "k8s-reference", mut_vault)
        assert not (mut_vault / "resources" / "kubernetes-notes.md").exists()

    def test_new_file_has_updated_title_in_frontmatter(self, mut_vault: Path) -> None:
        new_path = rename_note("resources/kubernetes-notes.md", "k8s-reference", mut_vault)
        content = (mut_vault / new_path).read_text()
        assert "k8s-reference" in content

    def test_wikilinks_updated_in_referencing_notes(self, mut_vault: Path) -> None:
        # helm-charts.md links to [[kubernetes-notes]] — should become [[k8s-reference]]
        rename_note("resources/kubernetes-notes.md", "k8s-reference", mut_vault)
        helm_content = (mut_vault / "resources" / "helm-charts.md").read_text()
        assert "[[k8s-reference]]" in helm_content
        assert "[[kubernetes-notes]]" not in helm_content

    def test_missing_note_raises(self, mut_vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            rename_note("resources/ghost.md", "new-title", mut_vault)


class TestDeleteNote:
    def test_note_moved_to_archives(self, mut_vault: Path) -> None:
        result = delete_note("resources/kubernetes-notes.md", mut_vault)
        assert "archives" in result
        archived = list((mut_vault / "archives").glob("kubernetes-notes*.md"))
        assert len(archived) == 1

    def test_original_file_removed(self, mut_vault: Path) -> None:
        delete_note("resources/kubernetes-notes.md", mut_vault)
        assert not (mut_vault / "resources" / "kubernetes-notes.md").exists()

    def test_archive_contains_reason_in_frontmatter(self, mut_vault: Path) -> None:
        delete_note("resources/kubernetes-notes.md", mut_vault, reason="no longer relevant")
        archived = list((mut_vault / "archives").glob("kubernetes-notes*.md"))[0]
        content = archived.read_text()
        assert "no longer relevant" in content
        # reason should be in frontmatter (between --- markers)
        fm_end = content.find("\n---", 3)
        frontmatter = content[:fm_end]
        assert "no longer relevant" in frontmatter

    def test_missing_note_raises(self, mut_vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            delete_note("resources/ghost.md", mut_vault)


class TestFindReferences:
    def test_finds_wikilink_references(self, mut_vault: Path) -> None:
        results = find_references("kubernetes-notes", mut_vault)
        paths = [r["path"] for r in results]
        # helm-charts.md and argocd-gitops.md link to [[kubernetes-notes]]
        assert any("helm-charts" in p for p in paths)

    def test_returns_empty_for_unreferenced_title(self, mut_vault: Path) -> None:
        results = find_references("this-title-has-zero-references-xyz", mut_vault)
        assert results == []

    def test_text_mention_search(self, mut_vault: Path) -> None:
        # With include_text_mentions, should find notes that mention "kubernetes" as text
        results = find_references("kubernetes", mut_vault, include_text_mentions=True)
        assert len(results) > 0


class TestAppendToNote:
    def test_append_to_section(self, mut_vault: Path) -> None:
        append_to_note(
            "people/alex-chen.md",
            "New 1:1 entry.",
            mut_vault,
            section_header="1:1 Notes",
        )
        content = (mut_vault / "people" / "alex-chen.md").read_text()
        assert "New 1:1 entry." in content

    def test_dated_append(self, mut_vault: Path) -> None:
        from datetime import date
        today = date.today().isoformat()
        append_to_note(
            "people/alex-chen.md",
            "Important update.",
            mut_vault,
            section_header="1:1 Notes",
            dated=True,
        )
        content = (mut_vault / "people" / "alex-chen.md").read_text()
        assert f"### {today}" in content
        assert "Important update." in content
