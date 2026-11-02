"""Chroma HTTP client targeting."""

import io
import urllib.error
from email.message import EmailMessage

from services.chroma import ChromaClient


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_heartbeat_uses_chroma_service_url() -> None:
    seen: list[tuple[str, str | None]] = []

    def opener(request, timeout):  # noqa: ANN001
        header = request.get_header("Authorization")
        seen.append((request.full_url, header))
        return _Response(200)

    client = ChromaClient("chromadb", 8000, opener=opener)
    assert client.base_url == "http://chromadb:8000"
    assert client.heartbeat() is True
    assert seen == [("http://chromadb:8000/api/v2/heartbeat", None)]


def test_heartbeat_sends_bearer_token() -> None:
    seen: list[str | None] = []

    def opener(request, timeout):  # noqa: ANN001
        seen.append(request.get_header("Authorization"))
        return _Response(200)

    client = ChromaClient("chromadb", 8000, token="skill-token", opener=opener)
    assert client.heartbeat() is True
    assert seen == ["Bearer skill-token"]


def test_heartbeat_falls_back_when_v2_is_missing() -> None:
    calls: list[str] = []

    def opener(request, timeout):  # noqa: ANN001
        calls.append(request.full_url)
        if request.full_url.endswith("/api/v2/heartbeat"):
            raise urllib.error.HTTPError(
                request.full_url,
                404,
                "missing",
                EmailMessage(),
                io.BytesIO(b""),
            )
        return _Response(200)

    client = ChromaClient("chromadb", 8000, opener=opener)
    assert client.heartbeat() is True
    assert calls[-1].endswith("/api/v1/heartbeat")
