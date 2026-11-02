"""Measure document retrieval against a running Hermes API.

Loads tests/test_data/retrieval/corpus.json through POST /documents, asks every
question in questions.json through GET /documents/search, and prints hit rates
as JSON. Run it once per embedder (hash vectors, then the provider) and compare.

    HERMES_API_URL=http://127.0.0.1:8080 HERMES_API_TOKEN=... python scripts/eval_retrieval.py

The corpus ids are prefixed with `eval-` so they do not overwrite real documents.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "tests" / "test_data" / "retrieval"
PREFIX = "eval-"
LIMIT = 5


def main() -> int:
    base = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8080").rstrip("/")
    token = os.environ.get("HERMES_API_TOKEN", "")
    corpus = json.loads((DATA / "corpus.json").read_text(encoding="utf-8"))
    questions = json.loads((DATA / "questions.json").read_text(encoding="utf-8"))
    for doc in corpus:
        _call(base, token, "POST", "/documents", {"id": PREFIX + doc["id"], "text": doc["text"], "source": doc["source"]})
    first = 0
    within = 0
    misses: list[str] = []
    for item in questions:
        query = urllib.parse.urlencode({"q": item["q"], "limit": LIMIT})
        found = _call(base, token, "GET", f"/documents/search?{query}", None)
        ranked = [_doc_id(match) for match in found.get("matches", [])]
        expected = PREFIX + item["expect"]
        if ranked[:1] == [expected]:
            first += 1
        if expected in ranked:
            within += 1
        else:
            misses.append(item["q"])
    health = _call(base, token, "GET", "/health", None)
    report = {
        "embedder": health.get("retrieval", {}).get("embedder"),
        "collection": health.get("retrieval", {}).get("documents_collection"),
        "questions": len(questions),
        "hit_at_1": round(first / len(questions), 3),
        f"hit_at_{LIMIT}": round(within / len(questions), 3),
        "misses": misses,
    }
    print(json.dumps(report, indent=2))
    return 0


def _doc_id(match: dict[str, object]) -> str:
    value = match.get("source_id", match.get("id", ""))
    return value if isinstance(value, str) else ""


def _call(base: str, token: str, method: str, path: str, body: dict[str, object] | None) -> dict[str, object]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{base}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read() or b"{}")


if __name__ == "__main__":
    sys.exit(main())
