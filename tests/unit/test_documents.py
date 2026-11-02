"""Document save and search on the agent API."""

import json

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from chroma_fake import FakeChroma
from services.chroma import ChromaClient, ChromaError
from services.embed import DIMENSION, embed
from utils.settings import load_settings


def _settings():
    return load_settings({"HERMES_ENV": "test", "CHROMA_HOST": "chromadb", "CHROMA_PORT": "8000"})


def test_embed_ranks_shared_words_closer() -> None:
    left = embed("tuesday meeting")
    right = embed("meeting on tuesday")
    other = embed("quantum banana telescope")
    assert len(left) == DIMENSION
    assert _distance(left, right) < _distance(left, other)


def test_save_and_search_documents() -> None:
    chroma = FakeChroma()
    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=chroma))
    saved = client.post("/documents", json={"id": "note-1", "text": "tuesday meeting", "source": "notes/a.md"})
    assert saved.status_code == 201
    assert saved.json() == {"id": "note-1", "collection": "hermes-documents", "chunks": 1, "unchanged": False}
    text, vector, metadata = chroma.rows["note-1::0000"]
    assert text == "tuesday meeting"
    assert len(vector) == DIMENSION
    assert metadata["doc_id"] == "note-1"
    assert metadata["source"] == "notes/a.md"
    assert metadata["embedder"] == "hash-64"

    found = client.get("/documents/search", params={"q": "tuesday"})
    assert found.status_code == 200
    match = found.json()["matches"][0]
    assert match["id"] == "note-1::0000"
    assert match["source_id"] == "note-1"
    assert match["source"] == "notes/a.md"


def test_long_documents_are_chunked_and_resaving_replaces_old_chunks() -> None:
    chroma = FakeChroma()
    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=chroma))
    long_text = " ".join(f"Paragraph {index} explains step {index} of the restore." for index in range(200))
    first = client.post("/documents", json={"id": "runbook", "text": long_text})
    assert first.json()["chunks"] > 1
    assert len(chroma.rows) == first.json()["chunks"]

    short = client.post("/documents", json={"id": "runbook", "text": "Restore from the nightly snapshot."})
    assert short.json()["chunks"] == 1
    assert list(chroma.rows) == ["runbook::0000"]


def test_unchanged_document_is_not_embedded_again() -> None:
    chroma = FakeChroma()
    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=chroma))
    client.post("/documents", json={"id": "note-1", "text": "tuesday meeting"})
    again = client.post("/documents", json={"id": "note-1", "text": "tuesday meeting"})
    assert again.json()["unchanged"] is True
    assert chroma.upserts == 1
    moved = client.post("/documents", json={"id": "note-1", "text": "tuesday meeting", "source": "b.md"})
    assert moved.json()["unchanged"] is False
    assert chroma.upserts == 2


def test_resaving_removes_a_legacy_whole_document_row() -> None:
    chroma = FakeChroma()
    chroma.put_legacy("note-1", "old tuesday text", embed("old tuesday text"))
    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=chroma))
    client.post("/documents", json={"id": "note-1", "text": "new tuesday text"})
    assert list(chroma.rows) == ["note-1::0000"]


def test_invalid_document_id_is_rejected() -> None:
    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=FakeChroma()))
    response = client.post("/documents", json={"id": "../secret", "text": "nope"})
    assert response.status_code == 400
    chunk_like = client.post("/documents", json={"id": "note::0001", "text": "nope"})
    assert chunk_like.status_code == 400
    long_source = client.post("/documents", json={"id": "note-1", "text": "ok", "source": "x" * 201})
    assert long_source.status_code == 400


def test_chroma_failure_is_a_bad_gateway() -> None:
    class _Down(FakeChroma):
        def upsert_chunks(self, *args: object) -> None:
            raise ChromaError("down", 500)

    client = TestClient(create_app(_settings(), chroma_reachable=lambda: True, chroma_client=_Down()))
    response = client.post("/documents", json={"id": "note-1", "text": "tuesday"})
    assert response.status_code == 502
    assert "down" not in response.text


def test_embedding_failure_is_a_bad_gateway_and_keeps_the_old_chunks() -> None:
    from services.embedder import EmbeddingError

    class _Broken:
        name = "broken"
        dimension = None

        def embed_query(self, text: str) -> list[float]:
            raise EmbeddingError("provider secret", 500)

        def embed_passages(self, texts: list[str]) -> list[list[float]]:
            raise EmbeddingError("provider secret", 500)

    chroma = FakeChroma()
    chroma.put_legacy("note-1", "kept", embed("kept"))
    client = TestClient(
        create_app(_settings(), chroma_reachable=lambda: True, chroma_client=chroma, embedder=_Broken())
    )
    response = client.post("/documents", json={"id": "note-1", "text": "tuesday"})
    assert response.status_code == 502
    assert response.json()["detail"] == "Embedding request failed"
    assert "secret" not in response.text
    assert "note-1" in chroma.rows


class _Response:
    def __init__(self, status: int, payload: bytes) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_client_targets_the_collection_and_sends_the_bearer_token() -> None:
    seen: list[tuple[str, str | None, dict[str, object]]] = []

    def opener(request, timeout):  # noqa: ANN001
        body = json.loads(request.data or b"{}")
        seen.append((request.full_url, request.get_header("Authorization"), body))
        if request.full_url.endswith("/collections"):
            return _Response(200, b'{"id":"col-1"}')
        if request.full_url.endswith("/query"):
            payload = {
                "ids": [["note-1::0000"]],
                "documents": [["tuesday"]],
                "distances": [[0.1]],
                "metadatas": [[{"doc_id": "note-1", "chunk": 0, "source": "a.md"}]],
            }
            return _Response(200, json.dumps(payload).encode())
        if request.full_url.endswith("/get"):
            return _Response(200, json.dumps({"ids": ["note-1::0000"], "metadatas": [{"doc_id": "note-1"}]}).encode())
        return _Response(200, b"{}")

    client = ChromaClient("chroma-gate", 8000, token="0123456789abcdef", opener=opener, collection="docs-v2")
    client.upsert_chunks(["note-1::0000"], ["tuesday"], [[0.0] * DIMENSION], [{"doc_id": "note-1", "chunk": 0}])
    client.delete_source("doc_id", "note-1")
    assert client.source_metadatas("doc_id", "note-1") == [{"doc_id": "note-1"}]
    matches = client.query_documents([0.0] * DIMENSION, 1)

    assert seen[0][0].endswith("/api/v2/tenants/default_tenant/databases/default_database/collections")
    assert seen[0][1] == "Bearer 0123456789abcdef"
    assert seen[0][2] == {"name": "docs-v2", "get_or_create": True}
    assert seen[1][0].endswith("/collections/col-1/upsert")
    assert seen[1][2]["metadatas"] == [{"doc_id": "note-1", "chunk": 0}]
    assert seen[2][2] == {"where": {"doc_id": "note-1"}}
    assert seen[3][2] == {"ids": ["note-1"]}
    assert seen[4][0].endswith("/collections/col-1/get")
    assert "metadatas" in seen[5][2]["include"]
    assert matches == [
        {"id": "note-1::0000", "text": "tuesday", "distance": 0.1, "source_id": "note-1", "chunk": 0, "source": "a.md"}
    ]


def test_client_checks_the_dimension_only_when_it_is_fixed() -> None:
    def opener(request, timeout):  # noqa: ANN001
        if request.full_url.endswith("/collections"):
            return _Response(200, b'{"id":"col-1"}')
        return _Response(200, b'{"ids":[[]]}')

    fixed = ChromaClient("chroma-gate", 8000, opener=opener)
    with pytest.raises(ChromaError, match="dimension"):
        fixed.query_documents([0.0] * 3, 1)
    free = ChromaClient("chroma-gate", 8000, opener=opener, dimension=None)
    assert free.query_documents([0.1] * 1024, 1) == []


def _distance(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right, strict=True))
