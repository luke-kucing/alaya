"""Embedder: chunk notes by section, embed with nomic-embed-text-v1.5 (ONNX)."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
_model = None  # lazy-loaded singleton


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME, backend="onnx", trust_remote_code=True)
        logger.info("Embedding model loaded")
    return _model


@dataclass
class Chunk:
    path: str
    title: str
    tags: list[str]
    directory: str
    modified_date: str
    chunk_index: int
    text: str


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and return (metadata, body)."""
    meta: dict = {}
    if not content.startswith("---"):
        return meta, content

    end = content.find("\n---", 3)
    if end == -1:
        return meta, content

    fm_block = content[3:end].strip()
    body = content[end + 4:].lstrip("\n")

    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()

    return meta, body


def _parse_inline_tags(body: str) -> list[str]:
    """Extract #hashtags from the first non-empty tag line after frontmatter."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        tags = re.findall(r"#([\w-]+)", stripped)
        if tags and re.match(r"^(#[\w-]+ ?)+$", stripped):
            return tags
        break
    return []


def chunk_note(path: str, content: str) -> list[Chunk]:
    """Split a note into section-level chunks.

    Each ## header becomes its own chunk. Content before the first ## header
    is included as a preamble chunk if non-empty.
    """
    meta, body = _parse_frontmatter(content)
    title = meta.get("title", Path(path).stem)
    date = meta.get("date", "")
    directory = path.split("/")[0] if "/" in path else ""
    tags = _parse_inline_tags(body)

    lines = body.splitlines()

    sections: list[tuple[str, list[str]]] = []
    current_header = ""
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_lines and "".join(current_lines).strip():
                sections.append((current_header, current_lines))
            current_header = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines and "".join(current_lines).strip():
        sections.append((current_header, current_lines))

    if not sections:
        return [Chunk(
            path=path,
            title=title,
            tags=tags,
            directory=directory,
            modified_date=date,
            chunk_index=0,
            text=content.strip(),
        )]

    chunks = []
    for idx, (header, section_lines) in enumerate(sections):
        text = "\n".join(section_lines).strip()
        if not text:
            continue
        prefix = f"{header}\n" if header else ""
        chunks.append(Chunk(
            path=path,
            title=title,
            tags=tags,
            directory=directory,
            modified_date=date,
            chunk_index=idx,
            text=f"{prefix}{text}",
        ))

    return chunks


def embed_chunks(chunks: list[Chunk]) -> list[np.ndarray]:
    """Embed a list of chunks. Returns one ndarray per chunk."""
    model = _get_model()
    texts = [f"search_document: {c.text}" for c in chunks]
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [embeddings[i] for i in range(len(chunks))]
