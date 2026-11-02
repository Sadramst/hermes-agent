"""ASGI entrypoint used by uvicorn and the hermes-api console script."""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from api.app import create_app
from utils.runtime import check_runtime
from utils.settings import load_settings


def serve() -> FastAPI:
    """Load settings, run the capability startup check, and build the app."""
    settings = load_settings()
    check_runtime(settings)
    return create_app(settings)


def main() -> None:
    settings = load_settings()
    uvicorn.run(
        "api.server:serve",
        factory=True,
        host=settings.hermes_host,
        port=settings.hermes_port,
        log_level=settings.log_level.lower(),
        reload=settings.hermes_env == "dev",
    )
