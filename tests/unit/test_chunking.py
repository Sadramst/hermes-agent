"""Chunking, keyword fusion, and the retrieval settings."""

import pytest

from agent.core import _rejoin
from services.chunking import CHUNK_CHARS, chunk_id, chunk_text
from services.rerank import fuse
from utils.settings import SettingsError, load_settings


def test_short_text_is_one_chunk_and_blank_text_is_none() -> None:
    assert chunk_text("  one short note  ") == ["one short note"]
    assert chunk_text("   ") == []


def test_long_text_splits_at_boundaries_within_the_size_and_overlaps() -> None:
    sentences = [f"Sentence {index} covers the backup window for host {index}." for index in range(120)]
    text = " ".join(sentences)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= CHUNK_CHARS for chunk in chunks)
    assert all(chunk.endswith(".") for chunk in chunks[:-1])
    for left, right in zip(chunks, chunks[1:]):
        assert right[:40] in left
    assert _rejoin(chunks) == text


def test_paragraph_breaks_are_preferred() -> None:
    first = "Alpha " * 200
    second = "Beta " * 200
    chunks = chunk_text(f"{first.strip()}\n\n{second.strip()}")
    assert chunks[0].endswith("Alpha")


def test_unbroken_text_still_splits() -> None:
    chunks = chunk_text("x" * 4000)
    assert all(len(chunk) <= CHUNK_CHARS for chunk in chunks)
    assert sum(len(chunk) for chunk in chunks) >= 4000


def test_invalid_overlap_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=100, overlap=100)


def test_chunk_ids_cannot_collide_with_document_ids() -> None:
    assert chunk_id("runbook", 3) == "runbook::0003"


def test_fusion_lifts_an_exact_term_match_and_keeps_order_on_ties() -> None:
    matches = [
        {"id": "a", "text": "general notes about servers"},
        {"id": "b", "text": "unrelated text"},
        {"id": "c", "text": "set HERMES_RAG_MODE to soft"},
    ]
    assert [m["id"] for m in fuse("what does HERMES_RAG_MODE do", matches)] == ["c", "a", "b"]
    assert [m["id"] for m in fuse("nothing shared", matches)] == ["a", "b", "c"]
    assert fuse("", matches) == matches


def _base(**extra: str) -> dict[str, str]:
    values = {"HERMES_ENV": "test", "CHROMA_HOST": "chromadb"}
    values.update(extra)
    return values


def test_retrieval_settings_default_off_with_hash_collections() -> None:
    settings = load_settings(_base())
    assert settings.rag_mode == "off"
    assert settings.memory_index is False
    assert settings.embed_model is None
    assert settings.documents_collection == "hermes-documents"
    assert settings.memory_collection == "hermes-memory"


def test_a_provider_switches_to_the_v2_collections() -> None:
    settings = load_settings(
        _base(
            HERMES_EMBED_BASE_URL="https://embed.example/v1",
            HERMES_EMBED_MODEL="text-embed-1",
            HERMES_EMBED_API_KEY="0123456789abcdef",
            HERMES_RAG_MODE="SOFT",
            HERMES_MEMORY_INDEX="on",
        )
    )
    assert settings.documents_collection == "hermes-documents-v2"
    assert settings.memory_collection == "hermes-memory-v2"
    assert settings.rag_mode == "soft"
    assert settings.memory_index is True


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"HERMES_EMBED_MODEL": "text-embed-1"}, "must be set together"),
        (
            {
                "HERMES_EMBED_BASE_URL": "ftp://embed.example",
                "HERMES_EMBED_MODEL": "m",
                "HERMES_EMBED_API_KEY": "0123456789abcdef",
            },
            "HERMES_EMBED_BASE_URL",
        ),
        (
            {
                "HERMES_EMBED_BASE_URL": "https://embed.example",
                "HERMES_EMBED_MODEL": "m",
                "HERMES_EMBED_API_KEY": "short",
            },
            "HERMES_EMBED_API_KEY",
        ),
        ({"HERMES_RAG_MODE": "on"}, "HERMES_RAG_MODE"),
        ({"HERMES_MEMORY_INDEX": "yes"}, "HERMES_MEMORY_INDEX"),
        ({"HERMES_DOCUMENTS_COLLECTION": "bad name"}, "HERMES_DOCUMENTS_COLLECTION"),
        ({"HERMES_MEMORY_COLLECTION": "hermes-documents"}, "must differ"),
    ],
)
def test_invalid_retrieval_settings_are_rejected(extra: dict[str, str], message: str) -> None:
    with pytest.raises(SettingsError, match=message):
        load_settings(_base(**extra))
