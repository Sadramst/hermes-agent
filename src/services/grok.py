"""One POST of a task to the Grok webhook. The body is the task text."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from typing import Any

MAX_TASK_CHARS = 2000
TIMEOUT_SECONDS = 5.0
REJECTED_TEXT = "Grok did not accept the task."


class GrokError(RuntimeError):
    """Raised when Grok does not accept the task. The message never includes the URL."""

    def __init__(self) -> None:
        super().__init__(REJECTED_TEXT)


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    """Stop redirects so the alias token stays on the configured host."""

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def default_opener() -> urllib.request.OpenerDirector:
    """Return an opener that does not follow redirects."""
    return urllib.request.build_opener(_RejectRedirect())


class GrokClient:
    """Post one handoff. A 202 returns the id. Any other outcome raises."""

    def __init__(
        self,
        url: str,
        alias_token: str,
        secret: str,
        opener: Callable[..., Any] | None = None,
        timeout: float = TIMEOUT_SECONDS,
    ) -> None:
        self.url = url
        self.alias_token = alias_token
        self.secret = secret
        self.timeout = timeout
        self._opener = opener or default_opener()

    def send(self, task: str) -> str:
        """Return the handoff id when Grok answers 202."""
        if not task.strip() or len(task) > MAX_TASK_CHARS:
            raise GrokError()
        handoff_id = uuid.uuid4().hex
        status = self._post({"handoffId": handoff_id, "task": task})
        if status != 202:
            raise GrokError()
        return handoff_id

    def _post(self, payload: dict[str, str]) -> int:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("X-Agent-Alias-Token", self.alias_token)
        request.add_header("X-Hermes-Handoff", self.secret)
        try:
            with _open(self._opener, request, self.timeout) as response:
                _discard(response)
                return int(response.status)
        except urllib.error.HTTPError as exc:
            _discard(exc)
            return int(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        raise GrokError()


def _discard(response: object) -> None:
    """Read and drop a body so an error page cannot surface later."""
    read = getattr(response, "read", None)
    if callable(read):
        read()


def _open(opener: Callable[..., Any], request: urllib.request.Request, timeout: float) -> Any:
    """Open a request. OpenerDirector must be used through open(), not called."""
    open_request = getattr(opener, "open", None)
    if open_request is None:
        return opener(request, timeout=timeout)
    return open_request(request, timeout=timeout)
