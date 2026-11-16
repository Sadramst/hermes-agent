"""Streamable HTTP MCP mount for Telegram gateway and IDE MCP clients."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from agent.core import HermesAgent
from agent.tools import ARGUMENTS_TEXT
from api.mcp_tools import (
    COMPLETE,
    CURRENT_TIME,
    LIST_MEMORIES,
    LIST_SKILLS,
    RECALL,
    REMEMBER,
    SAVE_DOCUMENT,
    SEARCH_DOCUMENTS,
    SEARCH_MEMORY,
    call_tool,
)
from utils.auth import is_authorized
from utils.settings import Settings

MAX_MCP_REQUESTS = 60
MCP_WINDOW_SECONDS = 60.0
LIMIT_TEXT = "MCP request limit reached"
INSTRUCTIONS = (
    "Tools for your Hermes personal assistant: skills, memory keys/search, "
    "document RAG save/search, local time, and completions. "
    "Search results carry [label] citations."
)

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")
_TEST_HOSTS = ("testserver", "testclient")


@dataclass(frozen=True)
class McpMount:
    """ASGI app gated by the bearer token and the request cap, plus its session manager."""

    app: ASGIApp
    session_manager: object

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        async with self.session_manager.run():
            yield


class RequestWindow:
    """Process-wide sliding window. A full window refuses the call."""

    def __init__(self, limit: int = MAX_MCP_REQUESTS, window_seconds: float = MCP_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: deque[float] = deque()
        self._lock = Lock()

    def allow(self, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds
        with self._lock:
            while self._hits and self._hits[0] <= cutoff:
                self._hits.popleft()
            if len(self._hits) >= self.limit:
                return False
            self._hits.append(moment)
            return True


class McpGate:
    """Count the request, then require the Hermes bearer, then hand it to MCP."""

    def __init__(self, app: ASGIApp, token: str, window: RequestWindow) -> None:
        self.app = app
        self.token = token
        self.window = window

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not self.window.allow():
            await JSONResponse({"detail": LIMIT_TEXT}, status_code=429)(scope, receive, send)
            return
        header = Headers(scope=scope).get("authorization")
        if not is_authorized(header, self.token):
            await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def build_mcp_mount(agent: HermesAgent, settings: Settings, limit: int = MAX_MCP_REQUESTS) -> McpMount:
    """Build the `/mcp` app. The caller mounts it and enters `lifespan`."""
    token = settings.api_token
    if token is None:
        raise RuntimeError("HERMES_API_TOKEN is required when HERMES_MCP_ENABLED is on")
    server = MCPServer(name="Hermes", instructions=INSTRUCTIONS)
    _register(server, agent)
    asgi = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=_security(settings),
    )
    return McpMount(
        app=McpGate(asgi, token, RequestWindow(limit)),
        session_manager=server.session_manager,
    )


def _register(server: MCPServer, agent: HermesAgent) -> None:
    @server.tool(name="list_skills", description=LIST_SKILLS, structured_output=False)
    def list_skills() -> str:
        return call_tool(agent, "list_skills", {})

    @server.tool(name="recall", description=RECALL, structured_output=False)
    def recall(key: str) -> str:
        return call_tool(agent, "recall", {"key": key})

    @server.tool(name="remember", description=REMEMBER, structured_output=False)
    def remember(key: str, value: str) -> str:
        return call_tool(agent, "remember", {"key": key, "value": value})

    @server.tool(name="list_memories", description=LIST_MEMORIES, structured_output=False)
    def list_memories(prefix: str = "") -> str:
        return call_tool(agent, "list_memories", {"prefix": prefix})

    @server.tool(name="search_documents", description=SEARCH_DOCUMENTS, structured_output=False)
    def search_documents(q: str, limit: int = 5) -> str:
        return call_tool(agent, "search_documents", {"q": q, "limit": limit})

    @server.tool(name="save_document", description=SAVE_DOCUMENT, structured_output=False)
    def save_document(id: str, text: str, source: str = "") -> str:
        return call_tool(agent, "save_document", {"id": id, "text": text, "source": source})

    @server.tool(name="search_memory", description=SEARCH_MEMORY, structured_output=False)
    def search_memory(q: str, limit: int = 5) -> str:
        return call_tool(agent, "search_memory", {"q": q, "limit": limit})

    @server.tool(name="current_time", description=CURRENT_TIME, structured_output=False)
    def current_time() -> str:
        return call_tool(agent, "current_time", {})

    @server.tool(name="complete", description=COMPLETE, structured_output=False)
    def complete(prompt: str) -> str:
        return call_tool(agent, "complete", {"prompt": prompt})

    for name in MCP_TOOL_ORDER:
        tool = server._tool_manager.get_tool(name)
        if tool is None:
            raise RuntimeError(f"Missing MCP tool: {name}")
        _forbid_extra_keys(tool)


MCP_TOOL_ORDER = (
    "list_skills",
    "recall",
    "remember",
    "list_memories",
    "search_documents",
    "save_document",
    "search_memory",
    "current_time",
    "complete",
)


def _forbid_extra_keys(tool: object) -> None:
    metadata = tool.fn_metadata
    original = metadata.validate_arguments
    allowed = set(metadata.arg_model.model_fields)

    def validate(arguments: dict[str, object] | None) -> dict[str, object]:
        incoming = dict(arguments or {})
        if set(incoming) - allowed:
            raise ValidationError.from_exception_data(
                "Arguments",
                [
                    {
                        "type": "extra_forbidden",
                        "loc": ("arguments",),
                        "msg": ARGUMENTS_TEXT,
                        "input": incoming,
                    }
                ],
            )
        return original(incoming)

    object.__setattr__(metadata, "validate_arguments", validate)


def _security(settings: Settings) -> TransportSecuritySettings:
    hosts: list[str] = []
    origins: list[str] = []
    names = list(_LOCAL_HOSTS)
    if settings.hermes_env == "test":
        names.extend(_TEST_HOSTS)
    for name in names:
        _allow(hosts, origins, name, None)
    for item in settings.mcp_allowed_hosts:
        host, separator, port = item.rpartition(":")
        if separator and port.isdigit():
            _allow(hosts, origins, host, port)
        else:
            _allow(hosts, origins, item, None)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )


def _allow(hosts: list[str], origins: list[str], host: str, port: str | None) -> None:
    exact = host if port is None else f"{host}:{port}"
    hosts.extend([exact, f"{host}:*"])
    for scheme in ("http", "https"):
        origins.extend([f"{scheme}://{exact}", f"{scheme}://{host}:*"])
