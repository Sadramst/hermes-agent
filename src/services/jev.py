"""TypeSafe System One client. Hermes calls this. It does not call Hermes."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from services.model import _open, default_opener


class JevError(RuntimeError):
    """Raised when a System One request fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class JevResult:
    model: str
    answers: dict[str, Any]
    usage: dict[str, Any]


class JevClient:
    """POST one state and question pack to `/systemone`. Redirects are rejected."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        opener: Callable[..., Any] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self._opener = opener or default_opener()

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        """Return typed answers. `questions` must already be a fixed pack."""
        if not questions:
            raise ValueError("Jev questions are empty")
        status, body = self._json({"model": self.model, "state": state, "questions": questions})
        if status < 200 or status >= 300:
            raise JevError("Jev request failed", status)
        return _result(body, status)

    def _json(self, payload: dict[str, object]) -> tuple[int, bytes]:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/systemone",
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
            raise JevError("Jev is unreachable") from exc


def _result(body: bytes, status: int) -> JevResult:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise JevError("Jev returned invalid JSON", status) from exc
    if not isinstance(parsed, dict):
        raise JevError("Jev returned no answers", status)
    model = parsed.get("model")
    answers = parsed.get("answers")
    usage = parsed.get("usage")
    if not isinstance(model, str) or not model or not isinstance(answers, dict):
        raise JevError("Jev returned no answers", status)
    if usage is None:
        usage = {}
    if not isinstance(usage, dict):
        raise JevError("Jev returned no answers", status)
    return JevResult(model=model, answers=answers, usage=usage)
