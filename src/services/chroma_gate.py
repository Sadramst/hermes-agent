"""Bearer-token proxy in front of Chroma.

chromadb/chroma:1.0.0 does not enforce authentication. Production publishes no
Chroma port and places this process on the only network path to the database.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from utils.auth import is_authorized
from utils.settings import chroma_token_usable


class GateError(RuntimeError):
    """Raised when the gate is started without a usable token."""


def require_token(token: str) -> str:
    """Reject a missing, short, or whitespace-containing token."""
    if not chroma_token_usable(token):
        raise GateError("CHROMA_AUTH_TOKEN must be at least 16 characters and contain no whitespace")
    return token


def forward(
    method: str,
    path: str,
    body: bytes | None,
    content_type: str | None,
    upstream: str,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 10.0,
) -> tuple[int, bytes, str | None]:
    """Forward one request upstream and return status, body, and content type.

    The caller authorization header is not forwarded.
    """
    request = Request(f"{upstream}{path}", data=body, method=method)
    if content_type:
        request.add_header("Content-Type", content_type)
    try:
        with opener(request, timeout=timeout) as response:
            payload = response.read() if hasattr(response, "read") else b""
            response_type = response.headers.get("Content-Type") if hasattr(response, "headers") else None
            return int(response.status), payload, response_type
    except HTTPError as exc:
        payload = exc.read()
        response_type = exc.headers.get("Content-Type") if exc.headers else None
        return int(exc.code), payload, response_type
    except (URLError, TimeoutError, OSError):
        return 502, b"upstream unavailable", "text/plain"


def build_server(
    token: str,
    upstream: str,
    host: str = "0.0.0.0",
    port: int = 8000,
    opener: Callable[..., Any] = urlopen,
) -> ThreadingHTTPServer:
    """Return a listening proxy. The token is checked before the socket opens."""
    checked = require_token(token)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _proxy(self) -> None:
            if not is_authorized(self.headers.get("Authorization"), checked):
                self._send(401, b"unauthorized", "text/plain")
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length) if length else None
            status, payload, content_type = forward(
                self.command,
                self.path,
                body,
                self.headers.get("Content-Type"),
                upstream,
                opener=opener,
            )
            self._send(status, payload, content_type)

        do_GET = _proxy
        do_POST = _proxy
        do_PUT = _proxy
        do_DELETE = _proxy

        def _send(self, status: int, payload: bytes, content_type: str | None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type or "application/octet-stream")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, message_format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(token: str, upstream: str, host: str = "0.0.0.0", port: int = 8000) -> None:
    """Listen until the process is stopped. Raises GateError when the token is unusable."""
    build_server(token, upstream, host, port).serve_forever()


def main() -> None:
    token = os.environ.get("CHROMA_AUTH_TOKEN", "")
    upstream_host = os.environ.get("CHROMA_UPSTREAM_HOST", "chromadb")
    upstream_port = os.environ.get("CHROMA_UPSTREAM_PORT", "8000")
    port = int(os.environ.get("GATE_PORT", "8000"))
    try:
        serve(token, f"http://{upstream_host}:{upstream_port}", port=port)
    except GateError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
