"""Unit tests for the embedder — model is mocked to avoid loading weights in unit tests."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from alaya.index.embedder import chunk_note, embed_chunks, Chunk


class TestChunkNote:
    def test_single_chunk_for_note_without_sections(self, vault: Path) -> None:
        path = "ideas/voice-capture.md"
        content = (vault / path).read_text()
        chunks = chunk_note(path, content)
        assert len(chunks) >= 1

    def test_multi_section_note_produces_multiple_chunks(self, vault: Path) -> None:
        path = "projects/second-brain.md"
        content = (vault / path).read_text()
        chunks = chunk_note(path, content)
        # second-brain has Goal, Tasks, Notes, Links sections
        assert len(chunks) >= 4

    def test_chunk_has_required_fields(self, vault: Path) -> None:
        content = (vault / "projects/second-brain.md").read_text()
        chunks = chunk_note("projects/second-brain.md", content)
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.path
            assert chunk.text
            assert isinstance(chunk.chunk_index, int)

    def test_chunk_metadata_populated(self, vault: Path) -> None:
        content = (vault / "projects/second-brain.md").read_text()
        chunks = chunk_note("projects/second-brain.md", content)
        first = chunks[0]
        assert first.title == "second-brain"
        assert first.directory == "projects"
        assert "project" in first.tags or "python" in first.tags

    def test_chunk_text_contains_section_content(self, vault: Path) -> None:
        content = (vault / "projects/second-brain.md").read_text()
        chunks = chunk_note("projects/second-brain.md", content)
        all_text = " ".join(c.text for c in chunks)
        assert "FastMCP" in all_text

    def test_empty_sections_skipped(self) -> None:
        content = "---\ntitle: test\ndate: 2026-01-01\n---\n\n## Empty\n\n## HasContent\n\nSome content here.\n"
        chunks = chunk_note("test.md", content)
        texts = [c.text for c in chunks]
        assert any("Some content here." in t for t in texts)


class TestEmbedChunks:
    def test_returns_array_per_chunk(self, vault: Path) -> None:
        content = (vault / "projects/second-brain.md").read_text()
        chunks = chunk_note("projects/second-brain.md", content)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(len(chunks), 768).astype(np.float32)

        with patch("alaya.index.embedder._get_model", return_value=mock_model):
            embeddings = embed_chunks(chunks)

        assert len(embeddings) == len(chunks)
        assert all(isinstance(e, np.ndarray) for e in embeddings)

    def test_embedding_dimension_matches_model(self, vault: Path) -> None:
        content = (vault / "projects/second-brain.md").read_text()
        chunks = chunk_note("projects/second-brain.md", content)[:2]

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.rand(2, 768).astype(np.float32)

        with patch("alaya.index.embedder._get_model", return_value=mock_model):
            embeddings = embed_chunks(chunks)

        assert embeddings[0].shape == (768,)
