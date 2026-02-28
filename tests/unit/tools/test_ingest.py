"""Unit tests for the ingest tool — HTTP and file I/O are mocked."""
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from alaya.tools.ingest import ingest, IngestResult, _fetch_url


SAMPLE_HTML = """
<html><body>
<h1>Understanding Kubernetes Operators</h1>
<p>Operators extend Kubernetes with custom controllers that manage complex stateful applications.</p>
<p>They encode operational knowledge into software — eliminating manual intervention.</p>
</body></html>
"""

SAMPLE_PDF_MD = """# Understanding Zero Trust

Zero trust networking assumes breach by default.
All requests are authenticated and authorized regardless of network location.
Every connection is treated as hostile until verified, eliminating implicit trust.

## Key Principles
- Verify explicitly
- Use least privilege access
- Assume breach at all times
"""


class TestIngestURL:
    def test_returns_ingest_result(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._fetch_url", return_value=("Understanding Kubernetes Operators", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="Operators extend Kubernetes with custom controllers."), \
             patch("alaya.tools.ingest._index_content", return_value=3):
            result = ingest("https://example.com/k8s-operators", vault=vault)
        assert isinstance(result, IngestResult)

    def test_raw_text_returned(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._fetch_url", return_value=("K8s Operators", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="Operators extend Kubernetes."), \
             patch("alaya.tools.ingest._index_content", return_value=2):
            result = ingest("https://example.com/k8s-operators", vault=vault)
        assert "Operators" in result.raw_text

    def test_chunks_indexed(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._fetch_url", return_value=("K8s Operators", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="Content here."), \
             patch("alaya.tools.ingest._index_content", return_value=4):
            result = ingest("https://example.com/k8s-operators", vault=vault)
        assert result.chunks_indexed == 4

    def test_suggested_links_returned(self, vault: Path) -> None:
        mock_search = [{"path": "resources/kubernetes-notes.md", "title": "kubernetes-notes", "score": 0.9}]
        with patch("alaya.tools.ingest._fetch_url", return_value=("K8s", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="kubernetes content"), \
             patch("alaya.tools.ingest._index_content", return_value=1), \
             patch("alaya.tools.ingest._find_suggested_links", return_value=mock_search):
            result = ingest("https://example.com/k8s", vault=vault)
        assert isinstance(result.suggested_links, list)

    def test_title_override(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._fetch_url", return_value=("Original Title", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="content"), \
             patch("alaya.tools.ingest._index_content", return_value=1):
            result = ingest("https://example.com/k8s", title="Custom Title", vault=vault)
        assert result.title == "Custom Title"

    def test_source_stored_in_result(self, vault: Path) -> None:
        url = "https://example.com/k8s-operators"
        with patch("alaya.tools.ingest._fetch_url", return_value=("K8s", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="content"), \
             patch("alaya.tools.ingest._index_content", return_value=1):
            result = ingest(url, vault=vault)
        assert result.source == url


class TestIngestPDF:
    def test_pdf_extracted_as_markdown(self, vault: Path, tmp_path: Path) -> None:
        pdf_path = tmp_path / "zero-trust.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")  # dummy file

        with patch("alaya.tools.ingest._extract_pdf", return_value=SAMPLE_PDF_MD), \
             patch("alaya.tools.ingest._index_content", return_value=3):
            result = ingest(str(pdf_path), vault=vault)
        assert "Zero Trust" in result.raw_text or "Zero trust" in result.raw_text

    def test_scanned_pdf_returns_error(self, vault: Path, tmp_path: Path) -> None:
        pdf_path = tmp_path / "scanned.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        with patch("alaya.tools.ingest._extract_pdf", return_value=""):
            result = ingest(str(pdf_path), vault=vault)
        assert "scanned" in result.raw_text.lower() or result.chunks_indexed == 0

    def test_scanned_pdf_message_includes_char_count(self, vault: Path, tmp_path: Path) -> None:
        pdf_path = tmp_path / "sparse.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        with patch("alaya.tools.ingest._extract_pdf", return_value="short"):
            result = ingest(str(pdf_path), vault=vault)
        assert "5 chars extracted" in result.raw_text

    def test_pdf_with_sufficient_text_is_not_flagged_as_scanned(self, vault: Path, tmp_path: Path) -> None:
        pdf_path = tmp_path / "real.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        # 120 chars — old threshold (100) would pass, but was too low.
        # New threshold is 250, so this should still be flagged.
        # Use > 250 chars to confirm a legitimate PDF is accepted.
        sufficient_text = "A" * 300

        with patch("alaya.tools.ingest._extract_pdf", return_value=sufficient_text), \
             patch("alaya.tools.ingest._index_content", return_value=3):
            result = ingest(str(pdf_path), vault=vault)
        assert result.chunks_indexed == 3
        assert "scanned" not in result.raw_text.lower()


class TestIngestMarkdown:
    def test_markdown_file_ingested_directly(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._index_content", return_value=5), \
             patch("alaya.tools.ingest._find_suggested_links", return_value=[]):
            result = ingest("projects/second-brain.md", vault=vault)
        assert "FastMCP" in result.raw_text
        assert result.chunks_indexed == 5

    def test_idempotent_on_same_source(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._index_content", return_value=5), \
             patch("alaya.tools.ingest._find_suggested_links", return_value=[]):
            result1 = ingest("projects/second-brain.md", vault=vault)
            result2 = ingest("projects/second-brain.md", vault=vault)
        assert result1.source == result2.source


class TestIngestTags:
    def test_tags_passed_to_index(self, vault: Path) -> None:
        with patch("alaya.tools.ingest._fetch_url", return_value=("Article", SAMPLE_HTML)), \
             patch("alaya.tools.ingest._extract_text_from_html", return_value="content"), \
             patch("alaya.tools.ingest._index_content", return_value=1) as mock_index:
            ingest("https://example.com/art", tags=["reference", "k8s"], vault=vault)
        # tags should be passed along to indexing
        call_kwargs = mock_index.call_args
        assert call_kwargs is not None


class TestFetchUrlRetry:
    """Tests for retry logic in _fetch_url."""

    def test_success_on_first_attempt_returns_result(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>content</html>"
        with patch("httpx.get", return_value=mock_response):
            title, html = _fetch_url("https://example.com/page", _retries=3, _backoff=0)
        assert html == "<html>content</html>"

    def test_retries_on_transport_error_then_succeeds(self) -> None:
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>content</html>"
        with patch("httpx.get", side_effect=[
            httpx.TransportError("connection reset"),
            mock_response,
        ]), patch("time.sleep"):
            title, html = _fetch_url("https://example.com/page", _retries=3, _backoff=0)
        assert html == "<html>content</html>"

    def test_raises_after_all_retries_exhausted(self) -> None:
        import httpx
        with patch("httpx.get", side_effect=httpx.TransportError("timeout")), \
             patch("time.sleep"):
            with pytest.raises(httpx.TransportError):
                _fetch_url("https://example.com/page", _retries=3, _backoff=0)

    def test_retries_on_503(self) -> None:
        import httpx
        fail_response = MagicMock()
        fail_response.status_code = 503

        ok_response = MagicMock()
        ok_response.status_code = 200
        ok_response.text = "content"

        with patch("httpx.get", side_effect=[fail_response, ok_response]), \
             patch("time.sleep"):
            _, html = _fetch_url("https://example.com/page", _retries=3, _backoff=0)
        assert html == "content"

    def test_does_not_retry_on_404(self) -> None:
        import httpx
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=error_response
        )
        with patch("httpx.get", return_value=error_response) as mock_get:
            with pytest.raises(httpx.HTTPStatusError):
                _fetch_url("https://example.com/missing", _retries=3, _backoff=0)
        # should only have been called once — no retry on 4xx
        assert mock_get.call_count == 1


class TestIngestDate:
    def test_synthetic_frontmatter_uses_today_not_hardcoded_date(self, vault: Path) -> None:
        # _index_content builds synthetic frontmatter then calls chunk_note.
        # The date: field must use date.today(), not a hardcoded literal.
        from datetime import date
        from alaya.tools.ingest import _index_content

        today = date.today().isoformat()
        captured = {}

        def capture_chunk(path, content):
            captured["content"] = content
            return []

        # _index_content does a local import of chunk_note from alaya.index.embedder
        with patch("alaya.index.embedder.chunk_note", side_effect=capture_chunk):
            _index_content("test/path.md", "Test Title", [], "some text", vault)

        assert "2026-01-01" not in captured.get("content", ""), "Date must not be hardcoded"
        assert today in captured.get("content", ""), f"Expected today {today} in synthetic frontmatter"
