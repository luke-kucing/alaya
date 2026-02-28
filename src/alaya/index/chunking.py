"""Pluggable chunking strategies for note indexing."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from alaya.vault import parse_note
from alaya.index.embedder import Chunk


@dataclass
class ChunkConfig:
    max_tokens: int = 512
    overlap_tokens: int = 50
    min_chunk_tokens: int = 30


def _approx_tokens(text: str) -> int:
    """Approximate token count using word count (1 word ≈ 1.3 tokens)."""
    return int(len(text.split()) * 1.3)


def _make_chunk(path: str, text: str, idx: int, title: str, tags: list[str], date: str) -> Chunk:
    directory = path.split("/")[0] if "/" in path else ""
    return Chunk(
        path=path,
        title=title,
        tags=tags,
        directory=directory,
        modified_date=date,
        chunk_index=idx,
        text=text.strip(),
    )


class ChunkingStrategy(Protocol):
    def chunk(self, path: str, content: str, config: ChunkConfig) -> list[Chunk]: ...


class SectionChunker:
    """Split on ## headers. Sub-split long sections on paragraph boundaries."""

    def chunk(self, path: str, content: str, config: ChunkConfig) -> list[Chunk]:
        note = parse_note(content)
        title = note.title or Path(path).stem
        lines = note.body.splitlines()

        raw_sections: list[tuple[str, list[str]]] = []
        current_header = ""
        current_lines: list[str] = []

        for line in lines:
            if line.startswith("## "):
                if current_lines and "".join(current_lines).strip():
                    raw_sections.append((current_header, current_lines))
                current_header = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines and "".join(current_lines).strip():
            raw_sections.append((current_header, current_lines))

        if not raw_sections:
            return [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]

        chunks: list[Chunk] = []
        idx = 0
        for header, section_lines in raw_sections:
            text = "\n".join(section_lines).strip()
            if not text:
                continue
            prefix = f"{header}\n" if header else ""
            full_text = f"{prefix}{text}"

            if _approx_tokens(full_text) > config.max_tokens:
                sub_chunks = _split_on_paragraphs(full_text, config)
                for sub in sub_chunks:
                    chunks.append(_make_chunk(path, sub, idx, title, note.tags, note.date))
                    idx += 1
            else:
                chunks.append(_make_chunk(path, full_text, idx, title, note.tags, note.date))
                idx += 1

        return chunks or [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]


class SlidingWindowChunker:
    """Fixed-size token window with overlap. No structural awareness."""

    def chunk(self, path: str, content: str, config: ChunkConfig) -> list[Chunk]:
        note = parse_note(content)
        title = note.title or Path(path).stem
        words = note.body.split()

        if not words:
            return [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]

        # Convert token limits to approximate word counts
        window = max(1, int(config.max_tokens / 1.3))
        overlap = max(0, int(config.overlap_tokens / 1.3))
        step = max(1, window - overlap)

        chunks: list[Chunk] = []
        start = 0
        idx = 0
        while start < len(words):
            end = min(start + window, len(words))
            text = " ".join(words[start:end])
            if _approx_tokens(text) >= config.min_chunk_tokens or not chunks:
                chunks.append(_make_chunk(path, text, idx, title, note.tags, note.date))
                idx += 1
            start += step

        return chunks


class SemanticChunker:
    """Split on paragraph boundaries; merge short paragraphs; respect code blocks."""

    def chunk(self, path: str, content: str, config: ChunkConfig) -> list[Chunk]:
        note = parse_note(content)
        title = note.title or Path(path).stem
        paragraphs = _extract_paragraphs(note.body)

        if not paragraphs:
            return [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]

        # Merge short paragraphs up to max_tokens
        merged: list[str] = []
        current_parts: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            tokens = _approx_tokens(para)
            if current_tokens + tokens > config.max_tokens and current_parts:
                merged.append("\n\n".join(current_parts))
                current_parts = [para]
                current_tokens = tokens
            else:
                current_parts.append(para)
                current_tokens += tokens

        if current_parts:
            merged.append("\n\n".join(current_parts))

        chunks = [
            _make_chunk(path, text, idx, title, note.tags, note.date)
            for idx, text in enumerate(merged)
            if text.strip()
        ]
        return chunks or [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]


class DailyNoteChunker:
    """Split on ### sub-headers (date entries). Each entry is one chunk."""

    def chunk(self, path: str, content: str, config: ChunkConfig) -> list[Chunk]:
        note = parse_note(content)
        title = note.title or Path(path).stem
        lines = note.body.splitlines()

        raw_sections: list[tuple[str, list[str]]] = []
        current_header = ""
        current_lines: list[str] = []

        for line in lines:
            if line.startswith("### "):
                if current_lines and "".join(current_lines).strip():
                    raw_sections.append((current_header, current_lines))
                current_header = line[4:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines and "".join(current_lines).strip():
            raw_sections.append((current_header, current_lines))

        if not raw_sections:
            return [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]

        chunks = []
        for idx, (header, section_lines) in enumerate(raw_sections):
            text = "\n".join(section_lines).strip()
            if not text:
                continue
            full_text = f"{header}\n{text}" if header else text
            chunks.append(_make_chunk(path, full_text, idx, title, note.tags, note.date))

        return chunks or [_make_chunk(path, content.strip(), 0, title, note.tags, note.date)]


def select_strategy(path: str, content: str) -> ChunkingStrategy:
    """Choose the best chunking strategy based on path and content."""
    directory = path.split("/")[0] if "/" in path else ""
    if directory == "daily":
        return DailyNoteChunker()
    if "## " in content:
        return SectionChunker()
    return SlidingWindowChunker()


# --- helpers ---

def _split_on_paragraphs(text: str, config: ChunkConfig) -> list[str]:
    """Sub-split a text block on blank lines to stay under max_tokens."""
    paragraphs = _extract_paragraphs(text)
    result: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        tokens = _approx_tokens(para)
        if current_tokens + tokens > config.max_tokens and current_parts:
            result.append("\n\n".join(current_parts))
            current_parts = [para]
            current_tokens = tokens
        else:
            current_parts.append(para)
            current_tokens += tokens

    if current_parts:
        result.append("\n\n".join(current_parts))

    return result or [text]


def _extract_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs, keeping code blocks atomic."""
    paragraphs: list[str] = []
    current_lines: list[str] = []
    in_code_block = False

    for line in text.splitlines():
        if line.startswith("```"):
            in_code_block = not in_code_block
            current_lines.append(line)
            continue

        if in_code_block:
            current_lines.append(line)
            continue

        if line.strip() == "" and current_lines:
            block = "\n".join(current_lines).strip()
            if block:
                paragraphs.append(block)
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        block = "\n".join(current_lines).strip()
        if block:
            paragraphs.append(block)

    return paragraphs
