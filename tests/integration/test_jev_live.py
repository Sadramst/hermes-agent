"""One live System One call. Skipped unless a key is set, and excluded from default CI."""

import os

import pytest

from services.jev import JevClient


@pytest.mark.integration
def test_live_systemone_when_configured() -> None:
    key = os.environ.get("HERMES_JEV_API_KEY", "").strip()
    if not key:
        pytest.skip("HERMES_JEV_API_KEY is not set")
    result = JevClient(
        os.environ.get("HERMES_JEV_BASE_URL", "https://api.typesafe.ai/v1"),
        os.environ.get("HERMES_JEV_MODEL", "jev-1.13.0"),
        key,
    ).evaluate(
        {"request": "status"},
        {"is_status": {"type": "noul", "instructions": "Is the request a status check?"}},
    )
    assert result.model
    assert "is_status" in result.answers
