"""Split parsed pages into overlapping chunks for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from server.ingest.parse import ParsedPage

_enc = tiktoken.get_encoding("cl100k_base")
TARGET_TOKENS = 400
OVERLAP_TOKENS = 60
HEADING_RE = re.compile(r"^(#{1,3}|[A-Z][A-Z\s]{4,}:?)\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    page: int
    ordinal: int
    heading: str
    text: str
    figure: bytes | None


def _token_len(text: str) -> int:
    return len(_enc.encode(text))


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def chunk_page(page: ParsedPage, page_ordinal_start: int = 0) -> list[Chunk]:
    text = page.text.strip()
    if not text:
        return []

    # Extract the first heading if present
    heading = ""
    m = HEADING_RE.search(text)
    if m:
        heading = m.group(2).strip()[:120]

    sentences = _split_sentences(text)
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    ordinal = page_ordinal_start

    for sent in sentences:
        sent_tokens = _token_len(sent)
        if current_tokens + sent_tokens > TARGET_TOKENS and current:
            chunk_text = " ".join(current)
            chunks.append(Chunk(
                page=page.page, ordinal=ordinal,
                heading=heading, text=chunk_text,
                figure=page.figure if ordinal == page_ordinal_start else None,
            ))
            ordinal += 1
            # Keep overlap
            overlap: list[str] = []
            overlap_tokens = 0
            for s in reversed(current):
                t = _token_len(s)
                if overlap_tokens + t > OVERLAP_TOKENS:
                    break
                overlap.insert(0, s)
                overlap_tokens += t
            current = overlap
            current_tokens = overlap_tokens
        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(Chunk(
            page=page.page, ordinal=ordinal,
            heading=heading, text=" ".join(current),
            figure=page.figure if not chunks else None,
        ))
    return chunks


def chunk_pages(pages: list[ParsedPage]) -> list[Chunk]:
    result: list[Chunk] = []
    ordinal = 0
    for page in pages:
        new = chunk_page(page, page_ordinal_start=ordinal)
        result.extend(new)
        ordinal += len(new)
    return result
