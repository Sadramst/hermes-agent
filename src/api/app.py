"""HTTP application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from agent import __version__
from agent.core import HermesAgent, _health_payload
from agent.tools import ToolCall
from services.chroma import ChromaClient, ChromaError
from services.documents import MAX_LIMIT
from services.embedder import EmbeddingError, build_embedder
from services.model import ModelClient, ModelError, ModelNotConfigured
from utils.auth import is_authorized
from utils.logging import configure_logging
from utils.settings import Settings, load_settings


class DocumentBody(BaseModel):
    id: str
    text: str
    source: str = ""


class CompletionBody(BaseModel):
    prompt: str


class ToolCallBody(BaseModel):
    name: str
    arguments: dict[str, str] = Field(default_factory=dict)


class ToolRunBody(BaseModel):
    calls: list[ToolCallBody]


def create_app(
    settings: Settings | None = None,
    chroma_reachable: Callable[[], bool] | None = None,
    chroma_client: ChromaClient | None = None,
    model_client: ModelClient | None = None,
    jev_client: object | None = None,
    grok_client: object | None = None,
    mcp_limit: int | None = None,
    embedder: object | None = None,
    memory_chroma: object | None = None,
) -> FastAPI:
    """Build the ASGI app. Tests can inject settings, Chroma, and the model client."""
    resolved = settings or load_settings()
    logger = configure_logging(resolved.log_level)
    vectors = embedder if embedder is not None else build_embedder(resolved)
    client = chroma_client or ChromaClient(
        resolved.chroma_host,
        resolved.chroma_port,
        resolved.chroma_auth_token,
        collection=resolved.documents_collection,
        dimension=getattr(vectors, "dimension", None),
    )
    probe = chroma_reachable or client.heartbeat
    agent = HermesAgent(
        resolved,
        chroma_client=client,
        model_client=model_client,
        jev_client=jev_client,
        grok_client=grok_client,
        embedder=vectors,
        memory_chroma=memory_chroma,
    )
    mcp_mount = None
    if resolved.mcp_enabled:
        from api.mcp_http import MAX_MCP_REQUESTS, build_mcp_mount

        mcp_mount = build_mcp_mount(
            agent,
            resolved,
            MAX_MCP_REQUESTS if mcp_limit is None else mcp_limit,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if mcp_mount is None:
            yield
            return
        async with mcp_mount.lifespan():
            yield

    app = FastAPI(title="Hermes Agent", version=__version__, lifespan=lifespan)

    def require_api_credential(authorization: str | None = Header(default=None)) -> None:
        token = resolved.api_token
        if token is None:
            return
        if not is_authorized(authorization, token):
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/health")
    def health() -> dict[str, object]:
        reachable = bool(probe())
        logger.debug("http.health env=%s chroma_reachable=%s", resolved.hermes_env, reachable)
        return _health_payload(resolved, reachable)

    def call_collection(action: Callable[[], dict[str, object]], event: str) -> dict[str, object]:
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ChromaError as exc:
            logger.warning("%s env=%s status=%s", event, resolved.hermes_env, exc.status)
            raise HTTPException(status_code=502, detail="Chroma request failed") from exc
        except EmbeddingError as exc:
            logger.warning("%s env=%s embed_status=%s", event, resolved.hermes_env, exc.status)
            raise HTTPException(status_code=502, detail="Embedding request failed") from exc

    @app.post("/documents", status_code=201)
    def save_document(
        body: DocumentBody,
        _: None = Depends(require_api_credential),
    ) -> dict[str, object]:
        return call_collection(
            lambda: agent.save_document(body.id, body.text, body.source),
            "documents.write_failed",
        )

    @app.get("/documents/search")
    def search_documents(
        q: str,
        limit: int = Query(default=5, ge=1, le=MAX_LIMIT),
        _: None = Depends(require_api_credential),
    ) -> dict[str, object]:
        return call_collection(lambda: agent.search_documents(q, limit), "documents.search_failed")

    @app.get("/memory/search")
    def search_memory(
        q: str,
        limit: int = Query(default=5, ge=1, le=MAX_LIMIT),
        _: None = Depends(require_api_credential),
    ) -> dict[str, object]:
        return call_collection(lambda: agent.search_memory(q, limit), "memory.search_failed")

    @app.post("/tools")
    def run_tools(
        body: ToolRunBody,
        _: None = Depends(require_api_credential),
    ) -> dict[str, object]:
        try:
            results = agent.run_tools(
                [ToolCall(call.name, call.arguments) for call in body.calls]
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "results": [
                {"name": result.name, "status": result.status, "output": result.output}
                for result in results
            ]
        }

    @app.post("/completions")
    def complete(
        body: CompletionBody,
        _: None = Depends(require_api_credential),
    ) -> dict[str, object]:
        try:
            return agent.complete(body.prompt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ModelNotConfigured as exc:
            raise HTTPException(status_code=503, detail="Model provider is not configured") from exc
        except ModelError as exc:
            logger.warning("model.complete_failed env=%s status=%s", resolved.hermes_env, exc.status)
            raise HTTPException(status_code=502, detail="Model request failed") from exc

    if mcp_mount is None:
        def mcp_disabled() -> None:
            raise HTTPException(status_code=404, detail="Not Found")

        app.add_api_route("/mcp", mcp_disabled, methods=["GET", "POST", "DELETE"])
        app.add_api_route("/mcp/{rest:path}", mcp_disabled, methods=["GET", "POST", "DELETE"])
    else:
        # Rewrite /mcp → /mcp/ in-process so Starlette does not 307 (clients may drop Authorization).
        @app.middleware("http")
        async def bare_mcp_path(request: Request, call_next):  # noqa: ANN001
            if request.scope.get("path") == "/mcp":
                request.scope["path"] = "/mcp/"
            return await call_next(request)

        app.mount("/mcp", mcp_mount.app)

    return app
