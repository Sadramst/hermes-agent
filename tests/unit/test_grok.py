"""Grok webhook client. The body is the handoff id and the task."""

import json

import pytest

from services.grok import GrokClient, GrokError, REJECTED_TEXT, TIMEOUT_SECONDS, default_opener
from utils.settings import SettingsError, load_settings


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


WEBHOOK = "https://agent.example/v1/channels/hermes/task"
ALIAS = "0123456789abcdef"
SECRET = "fedcba9876543210"


def test_send_posts_the_task_and_returns_the_id_on_202() -> None:
    captured: dict[str, object] = {}

    def opener(request, timeout):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        captured["body"] = request.data
        captured["timeout"] = timeout
        return _Response(202)

    handoff_id = GrokClient(WEBHOOK, ALIAS, SECRET, opener=opener).send("read the notes")
    payload = json.loads(captured["body"])
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert captured["url"] == WEBHOOK
    assert captured["timeout"] == TIMEOUT_SECONDS
    assert headers["x-agent-alias-token"] == ALIAS
    assert headers["x-hermes-handoff"] == SECRET
    assert set(payload) == {"handoffId", "task"}
    assert payload["handoffId"] == handoff_id
    assert payload["task"] == "read the notes"
    assert ALIAS not in payload["task"]
    assert SECRET not in json.dumps(payload)


def test_a_non_202_and_a_network_error_stay_generic() -> None:
    def refused(request, timeout):  # noqa: ANN001
        return _Response(500)

    with pytest.raises(GrokError, match=REJECTED_TEXT) as caught:
        GrokClient(WEBHOOK, ALIAS, SECRET, opener=refused).send("read the notes")
    assert caught.value.__cause__ is None
    assert "500" not in str(caught.value)

    def down(request, timeout):  # noqa: ANN001
        raise TimeoutError("timed out talking to agent.example")

    with pytest.raises(GrokError, match=REJECTED_TEXT) as caught:
        GrokClient(WEBHOOK, ALIAS, SECRET, opener=down).send("read the notes")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "agent.example" not in str(caught.value)


def test_redirects_are_rejected() -> None:
    handlers = [handler for handler in default_opener().handlers if hasattr(handler, "redirect_request")]
    assert len(handlers) == 1
    assert handlers[0].redirect_request(None, None, 302, "found", {}, "https://other.example") is None


def test_handoff_settings_default_off_and_require_a_webhook_when_on() -> None:
    off = load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost"})
    assert off.grok_handoff == "off"
    assert off.grok_webhook_url is None
    assert off.grok_alias_token is None
    with pytest.raises(SettingsError, match="HERMES_GROK_HANDOFF"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_GROK_HANDOFF": "yes"})
    with pytest.raises(SettingsError, match="HERMES_GROK_WEBHOOK_URL"):
        load_settings({"HERMES_ENV": "dev", "CHROMA_HOST": "localhost", "HERMES_GROK_HANDOFF": "on"})
    for url in (
        "http://agent.example/v1/channels/hermes/task",
        "https://user:secret@agent.example/v1/channels/hermes/task",
        "https://agent.example/v1/channels/other/task",
    ):
        with pytest.raises(SettingsError, match="HERMES_GROK_WEBHOOK_URL"):
            load_settings(
                {
                    "HERMES_ENV": "dev",
                    "CHROMA_HOST": "localhost",
                    "HERMES_GROK_HANDOFF": "on",
                    "HERMES_GROK_WEBHOOK_URL": url,
                    "HERMES_GROK_ALIAS_TOKEN": ALIAS,
                    "HERMES_GROK_HANDOFF_SECRET": SECRET,
                }
            )
    ready = load_settings(
        {
            "HERMES_ENV": "dev",
            "CHROMA_HOST": "localhost",
            "HERMES_GROK_HANDOFF": "on",
            "HERMES_GROK_WEBHOOK_URL": WEBHOOK,
            "HERMES_GROK_ALIAS_TOKEN": ALIAS,
            "HERMES_GROK_HANDOFF_SECRET": SECRET,
        }
    )
    assert ready.grok_webhook_url == WEBHOOK
    assert ready.grok_alias_token == ALIAS
    cursor_alias = (
        "https://api.cursor.com/internal/agentsdk/agents/"
        "2b3aa7b2-3338-4820-840c-e338073f8643/engine/v1/channels/hermes/task"
    )
    cursor_ready = load_settings(
        {
            "HERMES_ENV": "dev",
            "CHROMA_HOST": "localhost",
            "HERMES_GROK_HANDOFF": "on",
            "HERMES_GROK_WEBHOOK_URL": cursor_alias,
            "HERMES_GROK_ALIAS_TOKEN": ALIAS,
            "HERMES_GROK_HANDOFF_SECRET": SECRET,
        }
    )
    assert cursor_ready.grok_webhook_url == cursor_alias
