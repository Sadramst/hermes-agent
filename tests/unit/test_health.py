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
    assert body["jev"]["configured"] is False
    assert body["jev"]["mode"] == "off"
    assert body["mcp"]["enabled"] is False
    assert body["grok"]["handoff"] == "off"
    assert body["jev"]["model"] == "jev-1.13.0"
    assert "api_key" not in body["jev"]


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


def test_health_omits_the_grok_alias_token() -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_GROK_HANDOFF": "ask",
            "HERMES_GROK_ALIAS_TOKEN": "0123456789abcdef",
        }
    )
    response = TestClient(create_app(settings, chroma_reachable=lambda: True)).get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["grok"]["handoff"] == "ask"
    assert "0123456789abcdef" not in response.text
    assert "webhook" not in response.text


def test_health_omits_the_jev_key() -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_JEV_MODE": "shadow",
            "HERMES_JEV_API_KEY": "0123456789abcdef",
        }
    )
    response = TestClient(create_app(settings, chroma_reachable=lambda: True)).get("/health")
    body = response.json()
    assert response.status_code == 200
    assert body["jev"]["configured"] is True
    assert body["jev"]["mode"] == "shadow"
    assert "0123456789abcdef" not in response.text
