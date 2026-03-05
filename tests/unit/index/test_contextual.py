"""Tests for contextual retrieval: chunk context prepending."""
from alaya.index.embedder import Chunk
from alaya.index.contextual import add_chunk_context, _build_context_prefix


def _make_chunk(**kwargs) -> Chunk:
    defaults = {
        "path": "resources/kubernetes.md",
        "title": "Kubernetes",
        "tags": ["devops", "containers"],
        "directory": "resources",
        "modified_date": "2026-03-01",
        "chunk_index": 0,
        "text": "Kubernetes is a container orchestration platform.",
    }
    defaults.update(kwargs)
    return Chunk(**defaults)


class TestBuildContextPrefix:
    def test_includes_title(self):
        chunk = _make_chunk()
        prefix = _build_context_prefix(chunk)
        assert "Kubernetes" in prefix

    def test_includes_directory(self):
        chunk = _make_chunk()
        prefix = _build_context_prefix(chunk)
        assert "resources" in prefix

    def test_includes_tags(self):
        chunk = _make_chunk()
        prefix = _build_context_prefix(chunk)
        assert "devops" in prefix
        assert "containers" in prefix

    def test_includes_section_header(self):
        chunk = _make_chunk(text="## Architecture\nK8s uses a master-worker architecture.")
        prefix = _build_context_prefix(chunk)
        assert "Architecture" in prefix

    def test_no_metadata_returns_empty(self):
        chunk = _make_chunk(title="", directory="", tags=[])
        prefix = _build_context_prefix(chunk)
        assert prefix == ""

    def test_ends_with_separator(self):
        chunk = _make_chunk()
        prefix = _build_context_prefix(chunk)
        assert prefix.endswith("\n\n")


class TestAddChunkContext:
    def test_prepends_context_to_text(self):
        chunks = [_make_chunk()]
        result = add_chunk_context(chunks)
        assert len(result) == 1
        assert result[0].text.startswith("From note: Kubernetes")
        assert "container orchestration" in result[0].text

    def test_preserves_original_text(self):
        original_text = "Kubernetes is a container orchestration platform."
        chunks = [_make_chunk(text=original_text)]
        result = add_chunk_context(chunks)
        assert original_text in result[0].text

    def test_preserves_metadata(self):
        chunks = [_make_chunk()]
        result = add_chunk_context(chunks)
        assert result[0].path == chunks[0].path
        assert result[0].title == chunks[0].title
        assert result[0].tags == chunks[0].tags
        assert result[0].chunk_index == chunks[0].chunk_index

    def test_multiple_chunks(self):
        chunks = [
            _make_chunk(chunk_index=0, text="First chunk."),
            _make_chunk(chunk_index=1, text="Second chunk."),
        ]
        result = add_chunk_context(chunks)
        assert len(result) == 2
        assert "First chunk." in result[0].text
        assert "Second chunk." in result[1].text

    def test_empty_list(self):
        assert add_chunk_context([]) == []
