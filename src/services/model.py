"""OpenAI-compatible completion client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

MAX_PROMPT_CHARS = 16_000


class ModelError(RuntimeError):
    """Raised when a completion request fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ModelNotConfigured(ModelError):
    """Raised when a completion is requested without provider settings."""


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
    """Send one chat completion to a provider configured by environment variables."""

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
