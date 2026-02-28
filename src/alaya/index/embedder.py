"""Embedder: chunk notes by section, embed with nomic-embed-text-v1.5 (fastembed)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from alaya.vault import parse_note

logger = logging.getLogger(__name__)

_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
_model = None  # lazy-loaded singleton


def _get_model():
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", _MODEL_NAME)
        from fastembed import TextEmbedding
        _model = TextEmbedding(_MODEL_NAME)
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


def chunk_note(path: str, content: str) -> list[Chunk]:
    """Split a note into section-level chunks.

    Each ## header becomes its own chunk. Content before the first ## header
    is included as a preamble chunk if non-empty.
    """
    note = parse_note(content)
    title = note.title or Path(path).stem
    date = note.date
    directory = path.split("/")[0] if "/" in path else ""
    tags = note.tags
    body = note.body

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
    """Embed a list of chunks. Returns one normalized float32 ndarray per chunk."""
    model = _get_model()
    # nomic-embed requires a task prefix; "search_document:" for indexed content
    texts = [f"search_document: {c.text}" for c in chunks]
    raw = np.array(list(model.embed(texts)))
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    normalized = (raw / np.where(norms == 0, 1, norms)).astype(np.float32)
    return [normalized[i] for i in range(len(chunks))]
