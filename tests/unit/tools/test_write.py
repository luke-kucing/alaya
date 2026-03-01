"""Unit tests for write tools."""
from pathlib import Path
from unittest.mock import patch

import pytest

from alaya.tools.write import create_note, append_to_note, update_tags, _load_template, _render_template, _build_note_content


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

    def test_duplicate_raises_file_exists_error(self, vault: Path) -> None:
        create_note(title="dupe note", directory="ideas", tags=[], body="original", vault=vault)
        with pytest.raises(FileExistsError, match="already exists"):
            create_note(title="dupe note", directory="ideas", tags=[], body="overwrite attempt", vault=vault)

    def test_empty_slug_title_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="alphanumeric"):
            create_note(title="!!!", directory="ideas", tags=[], body="", vault=vault)

    def test_dash_only_title_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="alphanumeric"):
            create_note(title="---", directory="ideas", tags=[], body="", vault=vault)

    def test_valid_title_with_special_chars_succeeds(self, vault: Path) -> None:
        # special chars stripped, leaving a valid slug
        path = create_note(title="hello! world?", directory="ideas", tags=[], body="", vault=vault)
        assert "hello" in path

    def test_invalid_tag_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="Invalid tag"):
            create_note(title="valid title", directory="ideas", tags=["bad:tag"], body="", vault=vault)

    def test_tag_with_colon_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="Invalid tag"):
            create_note(title="valid title", directory="ideas", tags=["key:value"], body="", vault=vault)

    def test_valid_tags_accepted(self, vault: Path) -> None:
        path = create_note(title="tagged note", directory="ideas", tags=["python", "my-tag", "tag_2"], body="", vault=vault)
        assert path.endswith(".md")


class TestTemplates:
    def test_load_template_returns_none_if_missing(self, vault: Path) -> None:
        assert _load_template(vault, "nonexistent") is None

    def test_load_template_reads_file(self, vault: Path) -> None:
        (vault / "templates").mkdir(exist_ok=True)
        (vault / "templates" / "meeting.md").write_text("Meeting: {title}\n")
        assert _load_template(vault, "meeting") == "Meeting: {title}\n"

    def test_render_template_replaces_variables(self) -> None:
        result = _render_template("Title: {title}, Date: {date}", title="My Note", date="2026-01-01")
        assert result == "Title: My Note, Date: 2026-01-01"

    def test_render_template_unknown_variable_left_intact(self) -> None:
        result = _render_template("{title} and {unknown}", title="T")
        assert "{unknown}" in result

    def test_create_note_uses_named_template(self, vault: Path) -> None:
        (vault / "templates").mkdir(exist_ok=True)
        (vault / "templates" / "meeting.md").write_text(
            "---\ntitle: {title}\ndate: {date}\n---\n{tags}\n\n## Agenda\n\n{body}\n"
        )
        path = create_note("Stand-Up", "ideas", ["scrum"], "Daily sync.", vault, template="meeting")
        content = (vault / path).read_text()
        assert "## Agenda" in content
        assert "Stand-Up" in content
        assert "#scrum" in content

    def test_create_note_falls_back_to_directory_template(self, vault: Path) -> None:
        (vault / "templates").mkdir(exist_ok=True)
        (vault / "templates" / "ideas.md").write_text("---\ntitle: {title}\ndate: {date}\n---\nIdea: {body}\n")
        path = create_note("Idea Note", "ideas", [], "cool idea", vault)
        content = (vault / path).read_text()
        assert "Idea: cool idea" in content

    def test_create_note_falls_back_to_default_template(self, vault: Path) -> None:
        (vault / "templates").mkdir(exist_ok=True)
        (vault / "templates" / "default.md").write_text("---\ntitle: {title}\ndate: {date}\n---\nDefault: {body}\n")
        path = create_note("Default Note", "projects", [], "body text", vault)
        content = (vault / path).read_text()
        assert "Default: body text" in content

    def test_create_note_inline_fallback_when_no_templates(self, vault: Path) -> None:
        # vault fixture has no templates/ directory
        path = create_note("Plain Note", "ideas", ["x"], "plain body", vault)
        content = (vault / path).read_text()
        assert "---" in content
        assert "plain body" in content


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

    # --- section_header (R-WR-03) ---

    def test_section_header_appends_under_section(self, vault: Path) -> None:
        # second-brain.md has a "## Notes" section
        append_to_note("projects/second-brain.md", "New section entry.", vault, section_header="Notes")
        content = (vault / "projects/second-brain.md").read_text()
        lines = content.splitlines()
        notes_idx = next(i for i, l in enumerate(lines) if l.strip() == "## Notes")
        # the appended text should appear after ## Notes, before the next ## header
        rest = "\n".join(lines[notes_idx:])
        assert "New section entry." in rest

    def test_section_header_missing_raises(self, vault: Path) -> None:
        with pytest.raises(ValueError, match="[Ss]ection"):
            append_to_note("projects/second-brain.md", "text", vault, section_header="Nonexistent Section")

    def test_section_header_inserts_before_next_section(self, vault: Path) -> None:
        # Content after ## Notes should appear before ## Links
        append_to_note("projects/second-brain.md", "Inserted line.", vault, section_header="Notes")
        content = (vault / "projects/second-brain.md").read_text()
        lines = content.splitlines()
        inserted_idx = next(i for i, l in enumerate(lines) if "Inserted line." in l)
        links_idx = next(i for i, l in enumerate(lines) if l.strip() == "## Links")
        assert inserted_idx < links_idx

    # --- dated (R-WR-03) ---

    def test_dated_prepends_date_header(self, vault: Path) -> None:
        from datetime import date
        today = date.today().isoformat()
        append_to_note("projects/second-brain.md", "Meeting note.", vault, dated=True)
        content = (vault / "projects/second-brain.md").read_text()
        assert f"### {today}" in content
        assert "Meeting note." in content

    def test_dated_with_section_header(self, vault: Path) -> None:
        from datetime import date
        today = date.today().isoformat()
        append_to_note(
            "projects/second-brain.md",
            "1:1 note.",
            vault,
            section_header="Notes",
            dated=True,
        )
        content = (vault / "projects/second-brain.md").read_text()
        assert f"### {today}" in content
        assert "1:1 note." in content


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
