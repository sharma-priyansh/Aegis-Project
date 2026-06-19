"""Structure-aware chunking for runbooks (RAG §8).

Splits markdown-ish runbooks on headings/steps with token-bounded overlap, so a matched
chunk corresponds to a coherent procedure step rather than an arbitrary window. Pure and
testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6}\s+.*|step\s*\d+[:.].*)$", re.IGNORECASE | re.MULTILINE)


@dataclass
class Chunk:
    text: str
    ordinal: int
    heading: str


def chunk_markdown(text: str, max_chars: int = 800, overlap_chars: int = 100) -> list[Chunk]:
    """Split on headings first, then size-bound each section with overlap."""
    text = text.strip()
    if not text:
        return []

    # Split into (heading, body) sections by heading lines.
    sections: list[tuple[str, str]] = []
    matches = list(_HEADING.finditer(text))
    if not matches:
        sections.append(("", text))
    else:
        for idx, m in enumerate(matches):
            heading = m.group().strip()
            start = m.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            sections.append((heading, text[start:end].strip()))

    chunks: list[Chunk] = []
    ordinal = 0
    for heading, body in sections:
        content = (heading + "\n" + body).strip() if heading else body
        for piece in _window(content, max_chars, overlap_chars):
            chunks.append(Chunk(text=piece, ordinal=ordinal, heading=heading))
            ordinal += 1
    return chunks


def _window(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text] if text else []
    out: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return out
