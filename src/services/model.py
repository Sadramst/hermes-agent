"""OpenAI-compatible completion and multi-step tool-calling chat client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

MAX_PROMPT_CHARS = 16_000


class ModelError(RuntimeError):
    """Raised when a completion request fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ModelNotConfigured(ModelError):
    """Raised when a completion is requested without provider settings."""


@dataclass(frozen=True)
class ModelToolCall:
    """One tool call requested by the assistant in a chat turn."""

    id: str
    name: str
    arguments: dict[str, str]


@dataclass(frozen=True)
class ModelTurn:
    """Assistant response from one chat completion step."""

    content: str
    tool_calls: list[ModelToolCall]


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Stop redirects so the provider credential stays on the configured host."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def default_opener() -> urllib.request.OpenerDirector:
    """Return an opener that does not follow redirects."""
    return urllib.request.build_opener(_RejectRedirect())


def check_prompt(prompt: str) -> str:
    """Reject an empty or oversized completion prompt."""
    if not prompt.strip():
        raise ValueError("Prompt is empty")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"Prompt exceeds {MAX_PROMPT_CHARS} characters")
    return prompt


class ModelClient:
    """Send chat completions (single-shot or multi-step with tools) to an OpenAI-compatible provider."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        opener: Callable[..., Any] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._opener = opener or default_opener()

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        """Return the assistant text for one user prompt."""
        status, body = self._json(
            {
                "model": model or self.model,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        if status < 200 or status >= 300:
            raise ModelError("Model request failed", status)
        return _completion_text(body, status)

    def chat(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> ModelTurn:
        """Send a multi-message chat request with optional OpenAI-compatible tool definitions."""
        payload: dict[str, object] = {
            "model": model or self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        status, body = self._json(payload)
        if status < 200 or status >= 300:
            raise ModelError("Model request failed", status)
        return _parse_turn(body, status)

    def _json(self, payload: dict[str, object]) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
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
            raise ModelError("Model provider is unreachable") from exc


def _open(opener: Callable[..., Any], request: urllib.request.Request, timeout: float) -> Any:
    """Open a request. OpenerDirector must be used through open(), not called."""
    open_request = getattr(opener, "open", None)
    if open_request is None:
        return opener(request, timeout=timeout)
    return open_request(request, timeout=timeout)


def _completion_text(body: bytes, status: int) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ModelError("Model returned invalid JSON", status) from exc
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelError("Model returned no completion", status)
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content:
        raise ModelError("Model returned no completion", status)
    return content


def _parse_turn(body: bytes, status: int) -> ModelTurn:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ModelError("Model returned invalid JSON", status) from exc
    choices = parsed.get("choices") if isinstance(parsed, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelError("Model returned no completion", status)
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ModelError("Model returned no completion", status)
    raw_content = message.get("content")
    content = raw_content.strip() if isinstance(raw_content, str) else ""
    tool_calls = _parse_tool_calls(message.get("tool_calls"), status)
    if not content and not tool_calls:
        raise ModelError("Model returned no completion", status)
    return ModelTurn(content=content, tool_calls=tool_calls)


def _parse_tool_calls(raw: object, status: int) -> list[ModelToolCall]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ModelError("Model returned invalid tool_calls", status)
    calls: list[ModelToolCall] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ModelError("Model returned invalid tool_calls", status)
        call_id = item.get("id")
        resolved_id = call_id if isinstance(call_id, str) and call_id else f"call_{index}"
        fn = item.get("function")
        if not isinstance(fn, dict):
            raise ModelError("Model returned invalid tool_calls", status)
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            raise ModelError("Model returned invalid tool_calls", status)
        raw_args = fn.get("arguments", "{}")
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError as exc:
                raise ModelError("Model returned invalid tool arguments JSON", status) from exc
        elif isinstance(raw_args, dict):
            parsed_args = raw_args
        else:
            raise ModelError("Model returned invalid tool arguments", status)
        if not isinstance(parsed_args, dict):
            raise ModelError("Model returned invalid tool arguments", status)
        str_args = {
            str(k): str(v) if not isinstance(v, str) else v
            for k, v in parsed_args.items()
        }
        calls.append(ModelToolCall(id=resolved_id, name=name, arguments=str_args))
    return calls
