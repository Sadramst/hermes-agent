"""Validation for the Chroma document collection."""

from __future__ import annotations

import re

ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
# Documents are chunked before embedding, so this caps request size, not one vector.
MAX_TEXT_CHARS = 100_000
MAX_SOURCE_CHARS = 200
MAX_QUERY_CHARS = 2_000
DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def check_document_id(doc_id: str) -> str:
    if not ID_PATTERN.fullmatch(doc_id):
        raise ValueError(f"Invalid document id: {doc_id}")
    return doc_id


def check_document_text(text: str) -> str:
    if not text.strip():
        raise ValueError("Document text is empty")
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError(f"Document text exceeds {MAX_TEXT_CHARS} characters")
    return text


def check_source(source: str) -> str:
    """A source is an optional label such as a file path or URL, shown with citations."""
    cleaned = " ".join(source.split())
    if len(cleaned) > MAX_SOURCE_CHARS:
        raise ValueError(f"Document source exceeds {MAX_SOURCE_CHARS} characters")
    return cleaned


def check_query(query: str) -> str:
    if not query.strip():
        raise ValueError("Search query is empty")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"Search query exceeds {MAX_QUERY_CHARS} characters")
    return query


def check_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"Search limit must be from 1 to {MAX_LIMIT}")
    return limit
