"""Unit tests for write tools."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.write import create_note, append_to_note, update_tags


class TestCreateNote:
    def test_creates_file_in_correct_dir(self, vault: Path) -> None:
        path = create_note(
            title="test note",
            directory="ideas",
            tags=["idea", "test"],
            body="Some content here.",
            vault=vault,
        )
        assert (vault / path).exists()
        assert "ideas" in path

    def test_frontmatter_contains_title_and_date(self, vault: Path) -> None:
        path = create_note(
            title="frontmatter check",
            directory="ideas",
            tags=[],
            body="",
            vault=vault,
        )
        content = (vault / path).read_text()
        assert "title:" in content
        assert "date:" in content

    def test_tags_written_inline(self, vault: Path) -> None:
        path = create_note(
            title="tagged note",
            directory="ideas",
            tags=["foo", "bar"],
            body="",
            vault=vault,
        )
        content = (vault / path).read_text()
        assert "#foo" in content
        assert "#bar" in content

    def test_body_written_to_file(self, vault: Path) -> None:
        path = create_note(
            title="body note",
            directory="resources",
            tags=[],
            body="This is the body content.",
            vault=vault,
        )
        content = (vault / path).read_text()
        assert "This is the body content." in content

    def test_invalid_directory_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            create_note(
                title="bad dir",
                directory="../../etc",
                tags=[],
                body="",
                vault=vault,
            )

    def test_returns_relative_path_string(self, vault: Path) -> None:
        path = create_note(
            title="path return",
            directory="ideas",
            tags=[],
            body="",
            vault=vault,
        )
        assert isinstance(path, str)
        assert not path.startswith("/")


class TestAppendToNote:
    def test_appends_text_to_existing_note(self, vault: Path) -> None:
        append_to_note("projects/second-brain.md", "New appended line.", vault)
        content = (vault / "projects/second-brain.md").read_text()
        assert "New appended line." in content

    def test_original_content_preserved(self, vault: Path) -> None:
        original = (vault / "projects/second-brain.md").read_text()
        append_to_note("projects/second-brain.md", "Appended.", vault)
        content = (vault / "projects/second-brain.md").read_text()
        assert original in content

    def test_missing_note_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            append_to_note("projects/ghost.md", "text", vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            append_to_note("../../etc/passwd", "text", vault)


class TestUpdateTags:
    def test_adds_new_tags(self, vault: Path) -> None:
        update_tags("projects/second-brain.md", add=["newtag"], remove=[], vault=vault)
        content = (vault / "projects/second-brain.md").read_text()
        assert "#newtag" in content

    def test_removes_existing_tags(self, vault: Path) -> None:
        # second-brain.md has #project #python #mcp
        update_tags("projects/second-brain.md", add=[], remove=["python"], vault=vault)
        content = (vault / "projects/second-brain.md").read_text()
        assert "#python" not in content

    def test_preserves_other_tags(self, vault: Path) -> None:
        update_tags("projects/second-brain.md", add=[], remove=["python"], vault=vault)
        content = (vault / "projects/second-brain.md").read_text()
        assert "#project" in content
        assert "#mcp" in content

    def test_remove_nonexistent_tag_is_noop(self, vault: Path) -> None:
        before = (vault / "projects/second-brain.md").read_text()
        update_tags("projects/second-brain.md", add=[], remove=["doesnotexist"], vault=vault)
        after = (vault / "projects/second-brain.md").read_text()
        assert before == after

    def test_missing_note_raises(self, vault: Path) -> None:
        with pytest.raises(FileNotFoundError):
            update_tags("projects/ghost.md", add=["x"], remove=[], vault=vault)

    def test_path_traversal_rejected(self, vault: Path) -> None:
        with pytest.raises(ValueError):
            update_tags("../../etc/passwd", add=[], remove=[], vault=vault)
