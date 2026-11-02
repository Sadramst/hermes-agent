"""Live Chroma checks. Skipped when the service is down."""

import os

import pytest

from services.chroma import ChromaClient
from utils.settings import load_settings


@pytest.mark.integration
def test_chroma_heartbeat_when_available() -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": os.environ.get("CHROMA_HOST", "127.0.0.1"),
            "CHROMA_PORT": os.environ.get("CHROMA_PORT", "8000"),
        }
    )
    client = ChromaClient(settings.chroma_host, settings.chroma_port, settings.chroma_auth_token)
    if not client.heartbeat():
        pytest.skip("ChromaDB is not reachable")
    assert client.heartbeat() is True
