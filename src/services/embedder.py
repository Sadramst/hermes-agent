"""Embedders for Hermes collections: the built-in hash vectors or an OpenAI-compatible provider."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from services.embed import DIMENSION, embed
from services.model import _open, default_opener

MAX_BATCH = 32
HASH_NAME = f"hash-{DIMENSION}"


class EmbeddingError(RuntimeError):
    """Raised when an embedding request fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class HashEmbedder:
    """Keyword-overlap vectors. No provider, no download, fixed dimension."""

    name = HASH_NAME
    dimension: int | None = DIMENSION

    def embed_query(self, text: str) -> list[float]:
        return embed(text)

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [embed(text) for text in texts]


class EmbeddingClient:
    """Call `POST {base}/embeddings`. Redirects are rejected so the key stays on the configured host."""

    dimension: int | None = None

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        *,
        input_type: bool = False,
        opener: Callable[..., Any] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.name = model
        self.api_key = api_key
        self.input_type = input_type
        self.timeout = timeout
        self._opener = opener or default_opener()

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            vectors.extend(self._embed(texts[start : start + MAX_BATCH], "passage"))
        return vectors

    def _embed(self, texts: list[str], kind: str) -> list[list[float]]:
        if not texts:
            return []
        payload: dict[str, object] = {"model": self.name, "input": texts}
        if self.input_type:
            payload["input_type"] = kind
        status, body = self._json(payload)
        if status < 200 or status >= 300:
            raise EmbeddingError("Embedding request failed", status)
        vectors = [_unit(vector) for vector in _vectors(body, len(texts), status)]
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise EmbeddingError("Embedding provider returned mixed dimensions", status)
        if self.dimension is None:
            self.dimension = width
        elif width != self.dimension:
            raise EmbeddingError("Embedding dimension changed", status)
        return vectors

    def _json(self, payload: dict[str, object]) -> tuple[int, bytes]:
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with _open(self._opener, request, self.timeout) as response:
                raw = response.read() if hasattr(response, "read") else b""
                return int(response.status), raw
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbeddingError("Embedding provider is unreachable") from exc


def build_embedder(settings: object) -> HashEmbedder | EmbeddingClient:
    """Return the provider client when all three embed settings are present, else hash vectors."""
    base_url = getattr(settings, "embed_base_url", None)
    model = getattr(settings, "embed_model", None)
    api_key = getattr(settings, "embed_api_key", None)
    if not (base_url and model and api_key):
        return HashEmbedder()
    return EmbeddingClient(
        base_url,
        model,
        api_key,
        input_type=bool(getattr(settings, "embed_input_type", False)),
    )


def _vectors(body: bytes, expected: int, status: int) -> list[list[float]]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EmbeddingError("Embedding provider returned invalid JSON", status) from exc
    data = parsed.get("data") if isinstance(parsed, dict) else None
    if not isinstance(data, list) or len(data) != expected:
        raise EmbeddingError("Embedding provider returned the wrong count", status)
    rows = sorted(data, key=lambda row: row.get("index", 0) if isinstance(row, dict) else 0)
    vectors: list[list[float]] = []
    for row in rows:
        vector = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError("Embedding provider returned no vector", status)
        if not all(isinstance(value, int | float) and not isinstance(value, bool) for value in vector):
            raise EmbeddingError("Embedding provider returned a non-numeric vector", status)
        vectors.append([float(value) for value in vector])
    return vectors


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise EmbeddingError("Embedding provider returned a zero vector")
    return [value / norm for value in vector]
