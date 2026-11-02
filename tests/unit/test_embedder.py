"""Embedding provider client and the hash fallback."""

import io
import json
import math
import urllib.error
from email.message import EmailMessage

import pytest

from services.embed import DIMENSION
from services.embedder import EmbeddingClient, EmbeddingError, HashEmbedder, build_embedder
from utils.settings import load_settings

KEY = "0123456789abcdef"


class _Response:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self._payload = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _client(handler, **kwargs) -> EmbeddingClient:  # noqa: ANN001
    return EmbeddingClient("https://embed.example/v1/", "text-embed-1", KEY, opener=handler, **kwargs)


def test_posts_the_model_and_inputs_and_returns_unit_vectors_in_index_order() -> None:
    seen: list[tuple[str, str | None, dict[str, object]]] = []

    def handler(request, timeout):  # noqa: ANN001
        seen.append((request.full_url, request.get_header("Authorization"), json.loads(request.data)))
        return _Response(
            200,
            {"data": [{"index": 1, "embedding": [0.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}]},
        )

    vectors = _client(handler).embed_passages(["first", "second"])
    assert seen[0][0] == "https://embed.example/v1/embeddings"
    assert seen[0][1] == f"Bearer {KEY}"
    assert seen[0][2] == {"model": "text-embed-1", "input": ["first", "second"]}
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    assert all(math.isclose(sum(v * v for v in vector), 1.0) for vector in vectors)


def test_input_type_is_sent_only_when_enabled() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request, timeout):  # noqa: ANN001
        body = json.loads(request.data)
        bodies.append(body)
        return _Response(200, {"data": [{"index": i, "embedding": [1.0, 0.0]} for i in range(len(body["input"]))]})

    _client(handler, input_type=True).embed_query("where is the runbook")
    _client(handler, input_type=True).embed_passages(["runbook text"])
    _client(handler).embed_query("plain")
    assert bodies[0]["input_type"] == "query"
    assert bodies[1]["input_type"] == "passage"
    assert "input_type" not in bodies[2]


def test_passages_are_sent_in_batches() -> None:
    sizes: list[int] = []

    def handler(request, timeout):  # noqa: ANN001
        count = len(json.loads(request.data)["input"])
        sizes.append(count)
        return _Response(200, {"data": [{"index": i, "embedding": [1.0, 1.0]} for i in range(count)]})

    assert len(_client(handler).embed_passages([f"chunk {i}" for i in range(70)])) == 70
    assert sizes == [32, 32, 6]


def test_errors_do_not_leak_the_provider_body() -> None:
    def failing(request, timeout):  # noqa: ANN001
        raise urllib.error.HTTPError(request.full_url, 401, "no", EmailMessage(), io.BytesIO(b"key secret"))

    with pytest.raises(EmbeddingError) as caught:
        _client(failing).embed_query("x")
    assert caught.value.status == 401
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{"index": 0, "embedding": []}]},
        {"data": [{"index": 0, "embedding": ["a", "b"]}]},
        {"data": [{"index": 0, "embedding": [0.0, 0.0]}]},
        {"nothing": True},
    ],
)
def test_malformed_vectors_are_rejected(payload: object) -> None:
    with pytest.raises(EmbeddingError):
        _client(lambda request, timeout: _Response(200, payload)).embed_query("x")


def test_a_changed_dimension_is_rejected() -> None:
    widths = iter([2, 3])

    def handler(request, timeout):  # noqa: ANN001
        return _Response(200, {"data": [{"index": 0, "embedding": [1.0] * next(widths)}]})

    client = _client(handler)
    client.embed_query("first")
    assert client.dimension == 2
    with pytest.raises(EmbeddingError, match="dimension"):
        client.embed_query("second")


def test_build_embedder_falls_back_to_hash_vectors() -> None:
    hashed = build_embedder(load_settings({"HERMES_ENV": "test", "CHROMA_HOST": "chromadb"}))
    assert isinstance(hashed, HashEmbedder)
    assert hashed.dimension == DIMENSION
    assert len(hashed.embed_query("tuesday")) == DIMENSION

    provider = build_embedder(
        load_settings(
            {
                "HERMES_ENV": "test",
                "CHROMA_HOST": "chromadb",
                "HERMES_EMBED_BASE_URL": "https://integrate.api.nvidia.com/v1",
                "HERMES_EMBED_MODEL": "nvidia/nemotron-3.5-embed-1b",
                "HERMES_EMBED_API_KEY": KEY,
                "HERMES_EMBED_INPUT_TYPE": "on",
            }
        )
    )
    assert isinstance(provider, EmbeddingClient)
    assert provider.input_type is True
    assert provider.dimension is None
