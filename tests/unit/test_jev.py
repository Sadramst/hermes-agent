"""System One client contract. No live TypeSafe call."""

import json
from pathlib import Path

import pytest

from services.jev import JevClient, JevError
from services.model import default_opener

FIXTURE = Path(__file__).resolve().parents[1] / "test_data" / "jev" / "choice_high.json"
KEY = "0123456789abcdef"


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


def test_evaluate_posts_systemone_and_sends_the_bearer_key() -> None:
    seen: list[tuple[str, str | None, bytes | None]] = []
    fixture = FIXTURE.read_bytes()

    def opener(request, timeout):  # noqa: ANN001
        seen.append((request.full_url, request.get_header("Authorization"), request.data))
        assert timeout == 10
        return _Response(200, fixture)

    result = JevClient(
        "https://api.typesafe.ai/v1",
        "jev-1.13.0",
        KEY,
        opener=opener,
    ).evaluate(
        {"request": "status"},
        {"which": {"type": "choice", "instructions": "Which skill fits?", "criteria": {"none": "None"}}},
    )

    assert result.model == "jev-1.13.0"
    assert result.answers["which"]["choice"] == "bootstrap-hermes-stack"
    assert seen[0][0] == "https://api.typesafe.ai/v1/systemone"
    assert seen[0][1] == f"Bearer {KEY}"
    payload = json.loads(seen[0][2] or b"{}")
    assert payload["model"] == "jev-1.13.0"
    assert payload["state"] == {"request": "status"}
    assert payload["questions"]["which"]["type"] == "choice"


def test_redirects_are_rejected() -> None:
    client = JevClient("https://api.typesafe.ai/v1", "jev-1.13.0", KEY)
    handlers = [handler for handler in client._opener.handlers if hasattr(handler, "redirect_request")]
    assert handlers
    assert handlers[0].redirect_request(None, None, 302, "found", {}, "https://other.example") is None
    assert type(client._opener) is type(default_opener())


def test_provider_failure_does_not_return_the_response_body() -> None:
    def opener(request, timeout):  # noqa: ANN001
        return _Response(429, b'{"error":"secret-upstream"}')

    with pytest.raises(JevError, match="Jev request failed") as caught:
        JevClient("https://api.typesafe.ai/v1", "jev-1.13.0", KEY, opener=opener).evaluate(
            {"request": "status"},
            {"which": {"type": "noul", "instructions": "Is this a request?"}},
        )
    assert caught.value.status == 429
    assert "secret-upstream" not in str(caught.value)


def test_invalid_json_is_rejected() -> None:
    def opener(request, timeout):  # noqa: ANN001
        return _Response(200, b"not-json")

    with pytest.raises(JevError, match="invalid JSON"):
        JevClient("https://api.typesafe.ai/v1", "jev-1.13.0", KEY, opener=opener).evaluate(
            "status",
            {"which": {"type": "noul", "instructions": "Is this a request?"}},
        )


def test_empty_questions_are_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        JevClient("https://api.typesafe.ai/v1", "jev-1.13.0", KEY).evaluate("status", {})
