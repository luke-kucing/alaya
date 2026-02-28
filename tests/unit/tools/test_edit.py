"""Unit tests for edit tools: replace_section, extract_section."""
from pathlib import Path

import pytest

from alaya.tools.edit import replace_section, extract_section


class TestReplaceSection:
    def test_replaces_section_content(self, vault: Path) -> None:
        replace_section(
            "projects/second-brain.md",
            section="Notes",
            new_content="Updated notes content.",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert "Updated notes content." in content

    def test_original_section_removed(self, vault: Path) -> None:
        replace_section(
            "projects/second-brain.md",
            section="Notes",
            new_content="New content.",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        # original notes content gone
        assert "FastMCP, zk CLI, LanceDB" not in content

    def test_other_sections_preserved(self, vault: Path) -> None:
        replace_section(
            "projects/second-brain.md",
            section="Notes",
            new_content="New content.",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert "## Goal" in content
        assert "## Tasks" in content
        assert "## Links" in content

    def test_section_header_preserved(self, vault: Path) -> None:
        replace_section(
            "projects/second-brain.md",
            section="Notes",
            new_content="New content.",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert "## Notes" in content

    def test_missing_section_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="SECTION_NOT_FOUND"):
            replace_section(
                "projects/second-brain.md",
                section="Nonexistent Section",
                new_content="content",
                vault=vault,
            )

    def test_missing_note_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            replace_section("projects/ghost.md", section="Goal", new_content="x", vault=vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            replace_section("../../etc/passwd", section="x", new_content="y", vault=vault)


class TestExtractSection:
    def test_creates_new_note(self, vault: Path) -> None:
        new_path = extract_section(
            source="projects/second-brain.md",
            section="Notes",
            new_title="second-brain-notes",
            new_directory="resources",
            vault=vault,
        )
        assert (vault / new_path).exists()

    def test_section_content_in_new_note(self, vault: Path) -> None:
        new_path = extract_section(
            source="projects/second-brain.md",
            section="Notes",
            new_title="second-brain-notes",
            new_directory="resources",
            vault=vault,
        )
        content = (vault / new_path).read_text()
        assert "FastMCP, zk CLI, LanceDB" in content

    def test_wikilink_left_in_original(self, vault: Path) -> None:
        extract_section(
            source="projects/second-brain.md",
            section="Notes",
            new_title="second-brain-notes",
            new_directory="resources",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert "[[second-brain-notes]]" in content

    def test_original_section_body_removed(self, vault: Path) -> None:
        extract_section(
            source="projects/second-brain.md",
            section="Notes",
            new_title="second-brain-notes",
            new_directory="resources",
            vault=vault,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert "FastMCP, zk CLI, LanceDB" not in content

    def test_missing_section_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="SECTION_NOT_FOUND"):
            extract_section(
                source="projects/second-brain.md",
                section="Nonexistent",
                new_title="x",
                new_directory="resources",
                vault=vault,
            )
