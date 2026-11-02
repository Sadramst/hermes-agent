"""In-memory stand-in for ChromaClient with real nearest-neighbor ranking."""

from __future__ import annotations

from services.chroma import _chunk_fields


class FakeChroma:
    def __init__(self, collection: str = "hermes-documents", server: dict[str, "FakeChroma"] | None = None) -> None:
        self.collection = collection
        self.rows: dict[str, tuple[str, list[float], dict[str, object]]] = {}
        self.queries: list[int] = []
        self.upserts = 0
        self._server = server if server is not None else {}
        self._server[collection] = self

    def bound_to(self, collection: str, dimension: int | None) -> "FakeChroma":
        return self._server.get(collection) or FakeChroma(collection, self._server)

    def heartbeat(self) -> bool:
        return True

    def upsert_chunks(
        self,
        ids: list[str],
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, object]],
    ) -> None:
        self.upserts += 1
        for row_id, text, embedding, metadata in zip(ids, texts, embeddings, metadatas, strict=True):
            self.rows[row_id] = (text, embedding, dict(metadata))

    def put_legacy(self, row_id: str, text: str, embedding: list[float]) -> None:
        """A row written before chunking: whole text, no metadata."""
        self.rows[row_id] = (text, embedding, {})

    def delete_source(self, field: str, value: str) -> None:
        for row_id in [key for key, (_, _, meta) in self.rows.items() if meta.get(field) == value]:
            del self.rows[row_id]
        self.rows.pop(value, None)

    def source_metadatas(self, field: str, value: str) -> list[dict[str, object]]:
        return [dict(meta) for _, _, meta in self.rows.values() if meta.get(field) == value]

    def page(self, offset: int, limit: int = 100) -> list[dict[str, object]]:
        items = sorted(self.rows.items())[offset : offset + limit]
        return [self._match(row_id, text, meta, None) for row_id, (text, _, meta) in items]

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        self.queries.append(limit)
        scored = sorted(
            (sum((a - b) ** 2 for a, b in zip(embedding, vector, strict=True)), row_id)
            for row_id, (_, vector, _) in self.rows.items()
        )
        return [
            self._match(row_id, self.rows[row_id][0], self.rows[row_id][2], distance)
            for distance, row_id in scored[:limit]
        ]

    @staticmethod
    def _match(row_id: str, text: str, meta: dict[str, object], distance: float | None) -> dict[str, object]:
        match: dict[str, object] = {"id": row_id, "text": text, "distance": distance}
        match.update(_chunk_fields(meta))
        return match
