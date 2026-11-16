"""Health endpoint contract."""

from fastapi.testclient import TestClient

from agent import __version__
from api.app import create_app
from utils.settings import load_settings


def _settings(token: str = "") -> object:
    return load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "CHROMA_PORT": "8000",
            "CHROMA_AUTH_TOKEN": token,
        }
    )


def test_health_reports_ok_environment_and_chroma_reachability() -> None:
    app = create_app(_settings(), chroma_reachable=lambda: True)
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__
    assert body["status"] == "ok"
    assert body["environment"] == "test"
    assert body["chroma"]["reachable"] is True
    assert body["chroma"]["host"] == "chromadb"
    assert body["chroma"]["port"] == 8000
    assert body["model"]["configured"] is False
    assert body["model"]["name"] == ""
    assert body["provider"]["auth_mode"] == "api_key"
    assert body["provider"]["gemini_subscription"] == "pending_official_oauth"
    assert body["assistant"]["timezone"] == "UTC"
    assert body["mcp"]["enabled"] is False


def test_health_stays_ok_when_chroma_is_unreachable() -> None:
    app = create_app(_settings(), chroma_reachable=lambda: False)
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["chroma"]["reachable"] is False


def test_health_does_not_expose_auth_token() -> None:
    app = create_app(_settings("super-secret-token"), chroma_reachable=lambda: True)
    response = TestClient(app).get("/health")
    assert "super-secret-token" not in response.text
