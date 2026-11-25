"""Tests for vault.py shared utilities: parse_note, render_frontmatter."""
import pytest

from alaya.vault import parse_note, render_frontmatter, NoteMeta


class TestParseNote:
    def test_basic_frontmatter(self):
        content = "---\ntitle: My Note\ndate: 2026-01-01\n---\nBody text."
        note = parse_note(content)
        assert note.title == "My Note"
        assert note.date == "2026-01-01"
        assert note.body == "Body text."

    def test_tags_in_frontmatter(self):
        content = "---\ntitle: T\ntags: project python\n---\nBody."
        note = parse_note(content)
        assert note.tags == ["project", "python"]

    def test_inline_hashtags_when_no_frontmatter_tags(self):
        content = "---\ntitle: T\n---\n#project #python\nBody."
        note = parse_note(content)
        assert note.tags == ["project", "python"]

    def test_frontmatter_tags_take_precedence(self):
        content = "---\ntitle: T\ntags: alpha\n---\n#beta\nBody."
        note = parse_note(content)
        assert note.tags == ["alpha"]

    def test_no_frontmatter(self):
        content = "Just body text."
        note = parse_note(content)
        assert note.title == ""
        assert note.date == ""
        assert note.tags == []
        assert note.body == "Just body text."

    def test_extra_fields(self):
        content = "---\ntitle: T\narchived_reason: stale\n---\nBody."
        note = parse_note(content)
        assert note.extra["archived_reason"] == "stale"

    def test_value_with_colon(self):
        content = "---\ntitle: My Note: A Subtitle\n---\nBody."
        note = parse_note(content)
        assert note.title == "My Note: A Subtitle"

    def test_empty_value(self):
        content = "---\ntitle:\ndate: 2026-01-01\n---\nBody."
        note = parse_note(content)
        assert note.title == ""
        assert note.date == "2026-01-01"

    def test_body_stripped_of_leading_newlines(self):
        content = "---\ntitle: T\n---\n\n\nBody."
        note = parse_note(content)
        assert note.body.startswith("Body.")

    def test_unclosed_frontmatter_treated_as_body(self):
        content = "---\ntitle: T\nBody."
        note = parse_note(content)
        assert note.title == ""
        assert "---" in note.body


class TestParseInlineTagsBounds:
    def test_long_line_returns_empty(self):
        from alaya.vault import _parse_inline_tags, _MAX_TAG_LINE_LEN
        long_line = ("#tag " * (_MAX_TAG_LINE_LEN // 5 + 10)).strip()
        assert len(long_line) > _MAX_TAG_LINE_LEN
        assert _parse_inline_tags(long_line) == []

    def test_tag_count_capped_at_max(self):
        from alaya.vault import _parse_inline_tags, _MAX_TAGS
        # build a line with exactly MAX_TAGS + 5 short tags, under 500 chars
        tags = " ".join(f"#t{i}" for i in range(_MAX_TAGS + 5))
        result = _parse_inline_tags(tags)
        assert len(result) == _MAX_TAGS

    def test_normal_tags_still_parsed(self):
        from alaya.vault import _parse_inline_tags
        assert _parse_inline_tags("#python #fastmcp #notes") == ["python", "fastmcp", "notes"]

    def test_line_with_non_tag_content_returns_empty(self):
        from alaya.vault import _parse_inline_tags
        assert _parse_inline_tags("This is a sentence, not tags.") == []


class TestRenderFrontmatter:
    def test_basic(self):
        meta = {"title": "My Note", "date": "2026-01-01"}
        result = render_frontmatter(meta)
        assert result == "---\ntitle: My Note\ndate: 2026-01-01\n---\n"

    def test_empty_value(self):
        meta = {"title": "T", "archived_reason": ""}
        result = render_frontmatter(meta)
        assert "archived_reason:\n" in result

    def test_value_with_colon(self):
        meta = {"title": "My Note: Sub"}
        result = render_frontmatter(meta)
        assert 'title: "My Note: Sub"\n' in result


TRICKY_TITLES = ["foo: bar", "#hashtag start", 'say "hi"', "back\\slash: x", "it's [odd]", "plain"]


class TestTitleRoundTrip:
    """#151: titles with YAML specials are quoted on write and unquoted on read."""

    @pytest.mark.parametrize("title", TRICKY_TITLES)
    def test_create_note_round_trips(self, tmp_path, title):
        import yaml
        from alaya.tools.write import create_note

        rel = create_note(title, "ideas", [], "body", tmp_path)
        content = (tmp_path / rel).read_text()
        assert parse_note(content).title == title
        fm = content.split("---")[1]
        assert yaml.safe_load(fm)["title"] == title  # what zk/Obsidian see

    @pytest.mark.parametrize("title", TRICKY_TITLES)
    def test_rename_note_round_trips(self, tmp_path, title):
        from alaya.tools.structure import rename_note
        from alaya.tools.write import create_note

        rel = create_note("start", "ideas", [], "body", tmp_path)
        new_rel = rename_note(rel, title, tmp_path)
        assert parse_note((tmp_path / new_rel).read_text()).title == title

    def test_single_quoted_title_unquoted(self):
        assert parse_note("---\ntitle: 'it''s'\n---\n").title == "it's"
