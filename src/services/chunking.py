"""Split document text into overlapping chunks for embedding."""

from __future__ import annotations

import hashlib

CHUNK_CHARS = 1_500
OVERLAP_CHARS = 200
# Earliest point in a window where a break is accepted, so chunks do not shrink to fragments.
MIN_BREAK_FRACTION = 0.5
_BREAKS = ("\n\n", "\n", ". ", "? ", "! ", "; ", " ")


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    """Return stripped chunks of at most `size` characters. Short text is one chunk."""
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must exceed the overlap")
    body = text.strip()
    if not body:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(body):
        end = min(start + size, len(body))
        if end < len(body):
            end = _break_before(body, start, end, size)
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(body):
            break
        start = max(end - overlap, start + 1)
        while start < end and not body[start - 1].isspace():
            start += 1
    return chunks


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_id(doc_id: str, index: int) -> str:
    """Chunk ids use `::`, which document ids and memory keys cannot contain."""
    return f"{doc_id}::{index:04d}"


def _break_before(body: str, start: int, end: int, size: int) -> int:
    floor = start + int(size * MIN_BREAK_FRACTION)
    for mark in _BREAKS:
        found = body.rfind(mark, floor, end)
        if found != -1:
            return found + len(mark)
    return end
