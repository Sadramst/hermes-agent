"""Token gate in front of Chroma."""

import threading
import urllib.error
import urllib.request

import pytest

from services.chroma_gate import GateError, build_server, forward, is_authorized, require_token

TOKEN = "0123456789abcdef"


def test_short_token_is_rejected() -> None:
    with pytest.raises(GateError):
        require_token("short")


def test_authorization_header_must_match_the_bearer_token() -> None:
    assert is_authorized(f"Bearer {TOKEN}", TOKEN) is True
    assert is_authorized("Bearer wrong-token-value", TOKEN) is False
    assert is_authorized(None, TOKEN) is False


def test_forward_does_not_send_the_caller_token() -> None:
    seen: list[str | None] = []

    class _Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def read(self) -> bytes:
            return b"{}"

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def opener(request, timeout):  # noqa: ANN001
        seen.append(request.get_header("Authorization"))
        return _Response()

    status, body, content_type = forward("GET", "/api/v2/heartbeat", None, None, "http://chromadb:8000", opener)
    assert status == 200
    assert body == b"{}"
    assert content_type == "application/json"
    assert seen == [None]


def test_gate_rejects_a_missing_token_and_proxies_a_valid_one() -> None:
    class _Upstream:
        status = 200
        headers = {"Content-Type": "text/plain"}

        def read(self) -> bytes:
            return b"ok"

        def __enter__(self) -> "_Upstream":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def opener(request, timeout):  # noqa: ANN001
        return _Upstream()

    server = build_server(TOKEN, "http://chromadb:8000", host="127.0.0.1", port=0, opener=opener)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v2/heartbeat", timeout=3)
        assert denied.value.code == 401

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v2/heartbeat",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
            assert response.read() == b"ok"
    finally:
        server.shutdown()
        thread.join(timeout=3)
