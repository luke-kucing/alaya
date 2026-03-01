"""Ingest tool: PDF, URL, and markdown file ingestion into LanceDB."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from fastmcp import FastMCP
from alaya.config import get_vault_root

_INGESTIBLE_SUFFIXES = {".pdf", ".md", ".txt"}
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _validate_url(url: str) -> None:
    """Reject non-HTTP schemes and private/loopback/link-local IP destinations.

    Called before making a request and again after redirect resolution so that
    open redirects to internal addresses are also caught.

    Raises ValueError for any disallowed URL.
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"Blocked URL scheme '{scheme}': only http/https are allowed")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"No hostname in URL: {url}")
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(f"Blocked private/internal IP address: {hostname}")
    except ValueError as exc:
        # re-raise only our own errors; a non-IP hostname raises ValueError in
        # ipaddress.ip_address() which we intentionally swallow here
        if "Blocked" in str(exc):
            raise
# Minimum extracted characters before a PDF is considered scanned.
# 250 chars is conservative (~2 short sentences) and avoids false-positives
# on sparse-but-valid PDFs like slide decks or cover pages.
_SCANNED_PDF_MIN_CHARS = 250


@dataclass
class IngestResult:
    title: str
    source: str
    raw_text: str
    chunks_indexed: int
    suggested_links: list[dict] = field(default_factory=list)


def _fetch_url(url: str, _retries: int = 3, _backoff: float = 1.0) -> tuple[str, str]:
    """Fetch a URL and return (title, html_content).

    Validates the URL before fetching and after any redirect to block SSRF.
    Retries up to _retries times with exponential backoff on transient errors
    (network failures and 5xx / 429 responses). 4xx client errors are not
    retried — they indicate a deterministic failure.
    """
    import time
    import httpx

    _validate_url(url)

    last_exc: Exception | None = None
    for attempt in range(_retries):
        try:
            response = httpx.get(url, timeout=30, follow_redirects=True)
            # validate the final URL after any redirects
            _validate_url(str(response.url))
            if response.status_code in {429, 500, 502, 503, 504} and attempt < _retries - 1:
                time.sleep(_backoff * (2 ** attempt))
                continue
            response.raise_for_status()
            # naive title extraction — trafilatura does the real work
            title = url.split("/")[-1] or url
            return title, response.text
        except httpx.TransportError as exc:
            last_exc = exc
            if attempt < _retries - 1:
                time.sleep(_backoff * (2 ** attempt))

    raise last_exc or httpx.HTTPError(f"Failed to fetch {url} after {_retries} attempts")


def _extract_text_from_html(html: str, url: str = "") -> str:
    """Extract clean article text from HTML using trafilatura."""
    import trafilatura
    text = trafilatura.extract(html, url=url, include_links=False, include_images=False)
    return text or ""


def _extract_pdf(path: str) -> str:
    """Extract markdown from a PDF using pymupdf4llm."""
    import pymupdf4llm
    return pymupdf4llm.to_markdown(path)


def _index_content(
    path: str,
    title: str,
    tags: list[str],
    text: str,
    vault: Path,
) -> int:
    """Chunk and embed content into LanceDB. Returns number of chunks indexed."""
    from alaya.index.embedder import chunk_note, embed_chunks
    from alaya.index.store import get_store, upsert_note

    # build a synthetic note-like string for chunking
    tag_line = " ".join(f"#{t}" for t in tags) if tags else ""
    synthetic = f"---\ntitle: {title}\ndate: {date.today().isoformat()}\n---\n"
    if tag_line:
        synthetic += f"{tag_line}\n\n"
    synthetic += text

    rel = path if not path.startswith("/") else str(Path(path).relative_to(vault)) if path.startswith(str(vault)) else path
    chunks = chunk_note(rel, synthetic)
    if not chunks:
        return 0

    embeddings = embed_chunks(chunks)
    store = get_store(vault)
    upsert_note(rel, chunks, embeddings, store)
    return len(chunks)


def _find_suggested_links(text: str, vault: Path, limit: int = 5) -> list[dict]:
    """Find top semantically related existing notes for suggested wikilinks."""
    try:
        from alaya.index.embedder import get_model
        from alaya.index.store import get_store, hybrid_search
        import numpy as np

        model, cfg = get_model()
        raw = np.array(list(model.query_embed([f"{cfg.search_prefix}{text[:512]}"])))
        norm = np.linalg.norm(raw[0])
        embedding = (raw[0] / (norm if norm else 1)).astype(np.float32)
        store = get_store(vault)
        return hybrid_search(text[:200], embedding, store, limit=limit)
    except Exception:
        return []


def ingest(
    source: str,
    title: str | None = None,
    tags: list[str] | None = None,
    vault: Path | None = None,
) -> IngestResult:
    """Ingest a URL, PDF, or markdown file into LanceDB.

    Returns IngestResult with raw_text, title, source, chunks_indexed,
    suggested_links. Summary generation is Claude's responsibility.
    """
    if vault is None:
        vault = get_vault_root()

    tags = tags or []
    raw_text = ""
    resolved_title = title or source.split("/")[-1]

    # --- URL ---
    if source.startswith("http://") or source.startswith("https://"):
        fetched_title, html = _fetch_url(source)
        resolved_title = title or fetched_title
        raw_text = _extract_text_from_html(html, url=source)

    # --- file path ---
    else:
        path = Path(source)
        if not path.is_absolute():
            path = vault / source

        # Reject paths that escape the vault root (traversal or absolute paths
        # outside the vault such as /etc/passwd or ~/.ssh/id_rsa)
        try:
            path.resolve().relative_to(vault.resolve())
        except ValueError:
            return IngestResult(
                title=source.split("/")[-1],
                source=source,
                raw_text=f"Path escapes vault root: {source}",
                chunks_indexed=0,
            )

        suffix = path.suffix.lower()
        resolved_title = title or path.stem

        if suffix == ".pdf":
            raw_text = _extract_pdf(str(path))
            extracted_chars = len(raw_text.strip())
            if extracted_chars < _SCANNED_PDF_MIN_CHARS:
                return IngestResult(
                    title=resolved_title,
                    source=source,
                    raw_text=(
                        f"This PDF appears to be scanned ({extracted_chars} chars extracted). "
                        "OCR is not supported — consider copy-pasting the text manually."
                    ),
                    chunks_indexed=0,
                )
        elif suffix in {".md", ".txt"}:
            raw_text = path.read_text()
        else:
            return IngestResult(
                title=resolved_title,
                source=source,
                raw_text=f"Unsupported file type: {suffix}",
                chunks_indexed=0,
            )

    if not raw_text.strip():
        return IngestResult(
            title=resolved_title,
            source=source,
            raw_text="No content could be extracted from this source.",
            chunks_indexed=0,
        )

    chunks_indexed = _index_content(source, resolved_title, tags, raw_text, vault)
    suggested_links = _find_suggested_links(raw_text, vault)

    return IngestResult(
        title=resolved_title,
        source=source,
        raw_text=raw_text,
        chunks_indexed=chunks_indexed,
        suggested_links=suggested_links,
    )


# --- FastMCP tool registration ---

def _register(mcp: FastMCP, vault: Path) -> None:
    @mcp.tool()
    def ingest_tool(
        source: str,
        title: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """Ingest a URL, PDF, or markdown file. Returns raw_text, title, chunks indexed, and suggested wikilinks."""
        result = ingest(
            source,
            title=title or None,
            tags=tags or [],
            vault=vault,
        )
        links = "\n".join(f"- [[{r['title']}]]" for r in result.suggested_links[:5])
        links_section = f"\n\n**Suggested links:**\n{links}" if links else ""
        return (
            f"**Title:** {result.title}\n"
            f"**Source:** {result.source}\n"
            f"**Chunks indexed:** {result.chunks_indexed}\n\n"
            f"**Raw content:**\n{result.raw_text}"
            f"{links_section}"
        )

