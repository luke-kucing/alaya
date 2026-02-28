"""Tests for pluggable chunking strategies."""
import pytest

from alaya.index.chunking import (
    ChunkConfig,
    SectionChunker,
    SlidingWindowChunker,
    SemanticChunker,
    DailyNoteChunker,
    select_strategy,
)
from alaya.index.embedder import Chunk


FRONTMATTER = "---\ntitle: Test Note\ndate: 2026-01-01\n---\n"


class TestSectionChunker:
    def test_splits_on_h2_headers(self):
        content = FRONTMATTER + "## Intro\nIntro text.\n## Details\nDetail text."
        chunks = SectionChunker().chunk("notes/test.md", content, ChunkConfig())
        assert len(chunks) == 2
        assert "Intro" in chunks[0].text
        assert "Details" in chunks[1].text

    def test_preamble_before_first_header(self):
        content = FRONTMATTER + "Preamble text.\n## Section\nSection body."
        chunks = SectionChunker().chunk("notes/test.md", content, ChunkConfig())
        assert any("Preamble" in c.text for c in chunks)

    def test_single_chunk_when_no_headers(self):
        content = FRONTMATTER + "No headers here."
        chunks = SectionChunker().chunk("notes/test.md", content, ChunkConfig())
        assert len(chunks) == 1

    def test_long_section_subchunked_on_paragraphs(self):
        # A section exceeding max_tokens should be sub-split on blank lines
        long_para = "word " * 200  # ~200 words, well over 50 token limit
        content = FRONTMATTER + f"## Long\n{long_para}\n\n{long_para}"
        config = ChunkConfig(max_tokens=50)
        chunks = SectionChunker().chunk("notes/test.md", content, config)
        assert len(chunks) > 1

    def test_chunk_metadata(self):
        content = FRONTMATTER + "## Section\nBody."
        chunks = SectionChunker().chunk("notes/test.md", content, ChunkConfig())
        assert chunks[0].path == "notes/test.md"
        assert chunks[0].title == "Test Note"
        assert chunks[0].directory == "notes"

    def test_skips_empty_sections(self):
        content = FRONTMATTER + "## Empty\n\n## Real\nReal content."
        chunks = SectionChunker().chunk("notes/test.md", content, ChunkConfig())
        assert len(chunks) == 1
        assert "Real" in chunks[0].text


class TestSlidingWindowChunker:
    def test_short_content_single_chunk(self):
        content = FRONTMATTER + "Short text."
        chunks = SlidingWindowChunker().chunk("notes/test.md", content, ChunkConfig())
        assert len(chunks) == 1

    def test_long_content_multiple_chunks(self):
        content = FRONTMATTER + ("word " * 300)
        config = ChunkConfig(max_tokens=50, overlap_tokens=10)
        chunks = SlidingWindowChunker().chunk("notes/test.md", content, config)
        assert len(chunks) > 1

    def test_overlap_between_chunks(self):
        words = ["word"] * 100
        content = FRONTMATTER + " ".join(words)
        config = ChunkConfig(max_tokens=30, overlap_tokens=10)
        chunks = SlidingWindowChunker().chunk("notes/test.md", content, config)
        if len(chunks) > 1:
            # Last words of chunk 0 should appear in start of chunk 1
            end_words = chunks[0].text.split()[-5:]
            start_words = chunks[1].text.split()[:15]
            assert any(w in start_words for w in end_words)

    def test_min_chunk_size_filters_tiny_chunks(self):
        content = FRONTMATTER + "a b"  # very short
        config = ChunkConfig(min_chunk_tokens=10)
        chunks = SlidingWindowChunker().chunk("notes/test.md", content, config)
        # tiny content should still produce one chunk (not filtered away)
        assert len(chunks) >= 1


class TestSemanticChunker:
    def test_splits_on_paragraph_boundaries(self):
        # Each para is ~30 words; max_tokens=5 forces splits
        para = "word " * 30
        content = FRONTMATTER + f"{para.strip()}\n\n{para.strip()}\n\n{para.strip()}"
        config = ChunkConfig(max_tokens=5)
        chunks = SemanticChunker().chunk("notes/test.md", content, config)
        assert len(chunks) > 1

    def test_merges_short_paragraphs(self):
        content = FRONTMATTER + "Short.\n\nAlso short.\n\nThird short."
        config = ChunkConfig(max_tokens=100)
        chunks = SemanticChunker().chunk("notes/test.md", content, config)
        # short paragraphs should be merged into one chunk
        assert len(chunks) == 1

    def test_code_blocks_are_atomic(self):
        code = "```python\n" + "x = 1\n" * 50 + "```"
        content = FRONTMATTER + f"Intro.\n\n{code}\n\nOutro."
        config = ChunkConfig(max_tokens=30)
        chunks = SemanticChunker().chunk("notes/test.md", content, config)
        # code block should not be split
        code_chunks = [c for c in chunks if "```" in c.text]
        assert len(code_chunks) >= 1
        for c in code_chunks:
            assert c.text.count("```") % 2 == 0  # balanced delimiters


class TestDailyNoteChunker:
    def test_splits_on_h3_date_headers(self):
        content = FRONTMATTER + "### 2026-01-01\nMorning note.\n### 2026-01-02\nEvening note."
        chunks = DailyNoteChunker().chunk("daily/2026.md", content, ChunkConfig())
        assert len(chunks) == 2

    def test_single_chunk_when_no_h3(self):
        content = FRONTMATTER + "No date headers."
        chunks = DailyNoteChunker().chunk("daily/2026.md", content, ChunkConfig())
        assert len(chunks) == 1

    def test_chunk_contains_header_text(self):
        content = FRONTMATTER + "### 2026-01-01\nNotes for the day."
        chunks = DailyNoteChunker().chunk("daily/2026.md", content, ChunkConfig())
        assert "2026-01-01" in chunks[0].text


class TestSelectStrategy:
    def test_daily_directory_returns_daily(self):
        strategy = select_strategy("daily/2026-01-01.md", "## Section\nBody.")
        assert isinstance(strategy, DailyNoteChunker)

    def test_structured_note_returns_section(self):
        strategy = select_strategy("notes/work.md", "## Section\nBody.")
        assert isinstance(strategy, SectionChunker)

    def test_flat_note_returns_sliding_window(self):
        strategy = select_strategy("notes/flat.md", "No headers at all.")
        assert isinstance(strategy, SlidingWindowChunker)
