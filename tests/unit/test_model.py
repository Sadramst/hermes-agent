"""Completion client contract."""

import json

import pytest

from services.model import ModelClient, ModelError, check_prompt, default_opener


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


def test_completion_posts_to_the_provider_and_sends_the_bearer_key() -> None:
    seen: list[tuple[str, str | None, bytes | None]] = []

    def opener(request, timeout):  # noqa: ANN001
        seen.append((request.full_url, request.get_header("Authorization"), request.data))
        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": "ready"}}]}).encode()
        return _Response(200, body)

    text = ModelClient(
        "https://models.example/v1",
        "hermes-model",
        "0123456789abcdef",
        opener=opener,
    ).complete("status")

    assert text == "ready"
    assert seen[0][0] == "https://models.example/v1/chat/completions"
    assert seen[0][1] == "Bearer 0123456789abcdef"
    payload = json.loads(seen[0][2] or b"{}")
    assert payload["model"] == "hermes-model"
    assert payload["messages"] == [{"role": "user", "content": "status"}]


def test_completion_uses_the_opener_open_method() -> None:
    class _Opener:
        def open(self, request, timeout):  # noqa: ANN001
            assert request.full_url == "https://models.example/v1/chat/completions"
            assert timeout == 30
            body = json.dumps({"choices": [{"message": {"content": "ready"}}]}).encode()
            return _Response(200, body)

    text = ModelClient(
        "https://models.example/v1",
        "hermes-model",
        "0123456789abcdef",
        opener=_Opener(),
    ).complete("status")
    assert text == "ready"


def test_provider_failure_does_not_return_the_response_body() -> None:
    def opener(request, timeout):  # noqa: ANN001
        return _Response(401, b'{"error":"secret-upstream"}')

    with pytest.raises(ModelError, match="Model request failed") as caught:
        ModelClient("https://models.example/v1", "hermes-model", "0123456789abcdef", opener=opener).complete(
            "status"
        )
    assert caught.value.status == 401
    assert "secret-upstream" not in str(caught.value)


def test_redirects_are_rejected() -> None:
    handlers = [handler for handler in default_opener().handlers if hasattr(handler, "redirect_request")]
    assert len(handlers) == 1
    assert handlers[0].redirect_request(None, None, 302, "found", {}, "https://other.example") is None


def test_empty_prompt_is_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        check_prompt("   ")


def test_complete_accepts_per_call_model_override() -> None:
    seen: list[dict[str, object]] = []

    def opener(request, timeout):  # noqa: ANN001
        payload = json.loads(request.data or b"{}")
        seen.append(payload)
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
        return _Response(200, body)

    ModelClient(
        "https://models.example/v1",
        "hermes-model",
        "0123456789abcdef",
        opener=opener,
    ).complete("status", model="other-model")

    assert seen[0]["model"] == "other-model"
