"""HTTP client for a ChromaDB server on the Hermes Docker network."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from services.embed import DIMENSION


class ChromaError(RuntimeError):
    """Raised when a Chroma collection request fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ChromaClient:
    """Call the Chroma heartbeat API and one collection."""

    HEARTBEAT_PATHS = ("/api/v2/heartbeat", "/api/v1/heartbeat")
    COLLECTION_NAME = "hermes-documents"
    TENANT = "default_tenant"
    DATABASE = "default_database"
    PAGE_SIZE = 100

    def __init__(
        self,
        host: str,
        port: int,
        token: str | None = None,
        opener: Callable[..., Any] | None = None,
        timeout: float = 2.0,
        collection: str = COLLECTION_NAME,
        dimension: int | None = DIMENSION,
    ) -> None:
        self.host = host
        self.port = port
        self.token = token
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.collection = collection
        self.dimension = dimension
        self._opener = opener or urllib.request.urlopen
        self._collection_id: str | None = None

    def bound_to(self, collection: str, dimension: int | None) -> "ChromaClient":
        """Return a client for another collection on the same server and credential."""
        return ChromaClient(
            self.host,
            self.port,
            self.token,
            opener=self._opener,
            timeout=self.timeout,
            collection=collection,
            dimension=dimension,
        )

    def heartbeat(self) -> bool:
        """Return True when any configured heartbeat path responds with HTTP 2xx."""
        for path in self.HEARTBEAT_PATHS:
            status = self._status(path)
            if status is not None and 200 <= status < 300:
                return True
        return False

    def upsert_chunks(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, str | int]],
    ) -> None:
        """Insert or replace chunks. All four lists line up by index."""
        if not (len(ids) == len(texts) == len(embeddings) == len(metadatas)):
            raise ChromaError("Chunk columns do not line up")
        if not ids:
            return
        for embedding in embeddings:
            self._check_dimension(embedding)
        collection_id = self._ensure_collection()
        self._expect(
            "POST",
            self._collection_path(collection_id, "upsert"),
            {"ids": ids, "documents": texts, "embeddings": embeddings, "metadatas": metadatas},
        )

    def delete_source(self, field: str, value: str) -> None:
        """Delete every chunk whose metadata `field` equals value, plus a legacy whole-document row."""
        collection_id = self._ensure_collection()
        path = self._collection_path(collection_id, "delete")
        self._expect("POST", path, {"where": {field: value}})
        self._expect("POST", path, {"ids": [value]})

    def source_metadatas(self, field: str, value: str) -> list[dict[str, object]]:
        """Return the metadata of every chunk whose `field` equals value."""
        collection_id = self._ensure_collection()
        payload = self._expect(
            "POST",
            self._collection_path(collection_id, "get"),
            {"where": {field: value}, "include": ["metadatas"]},
        )
        return [row for row in _column(payload.get("metadatas")) if isinstance(row, dict)]

    def page(self, offset: int, limit: int = PAGE_SIZE) -> list[dict[str, object]]:
        """Return one page of stored rows with their text and metadata. An empty page is the end."""
        collection_id = self._ensure_collection()
        payload = self._expect(
            "POST",
            self._collection_path(collection_id, "get"),
            {"limit": limit, "offset": offset, "include": ["documents", "metadatas"]},
        )
        return _matches(payload)

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        """Return the nearest rows. Distance is smaller for a closer match."""
        self._check_dimension(embedding)
        collection_id = self._ensure_collection()
        payload = self._expect(
            "POST",
            self._collection_path(collection_id, "query"),
            {
                "query_embeddings": [embedding],
                "n_results": limit,
                "include": ["documents", "distances", "metadatas"],
            },
        )
        return _matches(payload)

    def _check_dimension(self, embedding: list[float]) -> None:
        if not embedding:
            raise ChromaError("Embedding is empty")
        if self.dimension is not None and len(embedding) != self.dimension:
            raise ChromaError("Embedding dimension does not match the collection")

    def _ensure_collection(self) -> str:
        if self._collection_id:
            return self._collection_id
        payload = self._expect(
            "POST",
            f"/api/v2/tenants/{self.TENANT}/databases/{self.DATABASE}/collections",
            {"name": self.collection, "get_or_create": True},
        )
        collection_id = payload.get("id")
        if not isinstance(collection_id, str) or not collection_id:
            raise ChromaError("Chroma did not return a collection id")
        self._collection_id = collection_id
        return collection_id

    def _collection_path(self, collection_id: str, action: str) -> str:
        return (
            f"/api/v2/tenants/{self.TENANT}/databases/{self.DATABASE}"
            f"/collections/{collection_id}/{action}"
        )

    def _expect(self, method: str, path: str, payload: dict[str, object]) -> dict[str, Any]:
        status, body = self._json(method, path, payload)
        if status < 200 or status >= 300:
            raise ChromaError("Chroma request failed", status)
        if not body:
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ChromaError("Chroma returned invalid JSON", status) from exc
        if not isinstance(parsed, dict):
            raise ChromaError("Chroma returned an unexpected payload", status)
        return parsed

    def _json(self, method: str, path: str, payload: dict[str, object]) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                raw = response.read() if hasattr(response, "read") else b""
                return int(response.status), raw
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChromaError("Chroma is unreachable") from exc

    def _status(self, path: str) -> int | None:
        request = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            return None


def _matches(payload: dict[str, Any]) -> list[dict[str, object]]:
    """Rows keep `id`, `text`, and `distance`. Chunk metadata adds `source_id`, `chunk`, and `source`."""
    ids = _column(payload.get("ids"))
    documents = _column(payload.get("documents"))
    distances = _column(payload.get("distances"))
    metadatas = _column(payload.get("metadatas"))
    matches: list[dict[str, object]] = []
    for index, row_id in enumerate(ids):
        if not isinstance(row_id, str):
            continue
        text = documents[index] if index < len(documents) else ""
        distance = distances[index] if index < len(distances) else None
        match: dict[str, object] = {
            "id": row_id,
            "text": text if isinstance(text, str) else "",
            "distance": float(distance) if isinstance(distance, (int, float)) else None,
        }
        metadata = metadatas[index] if index < len(metadatas) else None
        if isinstance(metadata, dict):
            match.update(_chunk_fields(metadata))
        matches.append(match)
    return matches


def _chunk_fields(metadata: dict[str, Any]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key in ("doc_id", "key"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            fields["source_id"] = value
            break
    chunk = metadata.get("chunk")
    if isinstance(chunk, int) and not isinstance(chunk, bool):
        fields["chunk"] = chunk
    source = metadata.get("source")
    if isinstance(source, str) and source:
        fields["source"] = source
    return fields


def _column(value: object) -> list[object]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return list(value[0])
    if isinstance(value, list):
        return list(value)
    return []
