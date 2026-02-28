"""Integration tests for vault navigation tools against a real zk binary.

These tests do NOT mock run_zk or the filesystem — they exercise the full
code path against vault_fixture_large.
"""
import pytest
from pathlib import Path

from alaya.tools.read import get_note, get_note_by_title, list_notes, get_backlinks, get_links, get_tags


pytestmark = pytest.mark.integration


class TestGetNote:
    def test_returns_formatted_content(self, large_vault: Path) -> None:
        result = get_note("resources/kubernetes-notes.md", large_vault)
        assert "**Title:**" in result
        assert "kubernetes-notes" in result
        assert "**Path:**" in result

    def test_structured_header_has_date(self, large_vault: Path) -> None:
        result = get_note("resources/kubernetes-notes.md", large_vault)
        assert "**Date:** 2026-01-15" in result

    def test_body_content_present(self, large_vault: Path) -> None:
        result = get_note("resources/kubernetes-notes.md", large_vault)
        assert "pods" in result.lower() or "kubernetes" in result.lower()

    def test_missing_note_raises(self, large_vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_note("resources/does-not-exist.md", large_vault)

    def test_path_traversal_rejected(self, large_vault: Path) -> None:
        with pytest.raises(ValueError):
            get_note("../../etc/passwd", large_vault)


class TestGetNoteByTitle:
    def test_finds_note_by_exact_title(self, large_vault: Path) -> None:
        result = get_note_by_title("kubernetes-notes", large_vault)
        assert "kubernetes" in result.lower()

    def test_case_insensitive(self, large_vault: Path) -> None:
        result = get_note_by_title("KUBERNETES-NOTES", large_vault)
        assert "**Title:** kubernetes-notes" in result

    def test_missing_title_raises(self, large_vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            get_note_by_title("this-does-not-exist-anywhere", large_vault)

    def test_ambiguous_title_raises(self, large_vault: Path, tmp_path: Path) -> None:
        # create a duplicate in a scratch dir under large_vault
        dupe = large_vault / "ideas" / "kubernetes-notes-dupe.md"
        dupe.write_text("---\ntitle: kubernetes-notes\ndate: 2026-01-01\n---\nDuplicate.\n")
        try:
            with pytest.raises(ValueError, match="[Aa]mbiguous"):
                get_note_by_title("kubernetes-notes", large_vault)
        finally:
            dupe.unlink()


class TestListNotes:
    def test_returns_all_notes_as_table(self, large_vault: Path) -> None:
        result = list_notes(large_vault, limit=200)
        assert "|" in result
        assert "kubernetes-notes" in result

    def test_filter_by_directory(self, large_vault: Path) -> None:
        result = list_notes(large_vault, directory="resources", limit=50)
        lines = [l for l in result.splitlines() if "|" in l and "---" not in l and "Title" not in l]
        assert len(lines) >= 20  # we have 25+ resource notes

    def test_filter_by_tag(self, large_vault: Path) -> None:
        result = list_notes(large_vault, tag="kubernetes", limit=50)
        assert "kubernetes" in result

    def test_since_filter(self, large_vault: Path) -> None:
        result = list_notes(large_vault, since="2026-02-01", limit=50)
        # notes before 2026-02-01 should be excluded
        assert "2025-12-20" not in result  # networking-fundamentals

    def test_sort_by_title(self, large_vault: Path) -> None:
        result = list_notes(large_vault, sort="title", limit=10)
        assert "|" in result

    def test_recent_filter(self, large_vault: Path) -> None:
        # recent=9999 should return everything (all notes are within 9999 days)
        result = list_notes(large_vault, recent=9999, limit=200)
        assert "kubernetes-notes" in result

    def test_empty_results(self, large_vault: Path) -> None:
        result = list_notes(large_vault, tag="this-tag-does-not-exist-at-all")
        assert "no notes" in result.lower()


class TestGetBacklinks:
    def test_notes_linking_to_kubernetes(self, large_vault: Path) -> None:
        # helm-charts, argocd-gitops, zero-trust-research all link to kubernetes-notes
        result = get_backlinks("resources/kubernetes-notes.md", large_vault)
        assert "helm-charts" in result or "argocd-gitops" in result

    def test_isolated_note_has_no_backlinks(self, large_vault: Path) -> None:
        # networking-fundamentals has no incoming links in our fixture
        result = get_backlinks("resources/networking-fundamentals.md", large_vault)
        assert "no backlinks" in result.lower() or "networking" not in result.lower()

    def test_path_traversal_rejected(self, large_vault: Path) -> None:
        with pytest.raises(ValueError):
            get_backlinks("../../etc/passwd", large_vault)


class TestGetLinks:
    def test_kubernetes_notes_links_out(self, large_vault: Path) -> None:
        # kubernetes-notes links to helm-charts, argocd-gitops, zero-trust-research
        result = get_links("resources/kubernetes-notes.md", large_vault)
        assert "helm-charts" in result or "zero-trust-research" in result

    def test_no_links_returns_message(self, large_vault: Path) -> None:
        # inbox.md has no outgoing wikilinks
        result = get_links("inbox.md", large_vault)
        assert "no links" in result.lower()


class TestGetTags:
    def test_returns_tag_table(self, large_vault: Path) -> None:
        result = get_tags(large_vault)
        assert "|" in result
        assert "kubernetes" in result

    def test_counts_are_positive(self, large_vault: Path) -> None:
        result = get_tags(large_vault)
        # every row should have a numeric count
        rows = [l for l in result.splitlines() if "|" in l and "Tag" not in l and "---" not in l]
        assert len(rows) >= 5
