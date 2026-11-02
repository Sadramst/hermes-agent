"""Cursor calls Hermes over MCP. Hermes does not call Cursor."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.decisions.guardrails import REVIEW_TEXT
from agent.tools import ARGUMENTS_TEXT, MISSING_TEXT
from api.mcp_http import LIMIT_TEXT, MAX_MCP_REQUESTS
from api.mcp_tools import MCP_TOOLS, REFUSED_TEXT, call_tool
from services.jev import JevResult
from utils.settings import SettingsError, load_settings

TOKEN = "fedcba9876543210"
MODEL_KEY = "0123456789abcdef"


def _base(tmp_path: Path, **extra: str) -> dict[str, str]:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "CHROMA_PORT": "8000",
        "HERMES_API_TOKEN": TOKEN,
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        "HERMES_MODEL_BASE_URL": "https://models.example/v1",
        "HERMES_MODEL_NAME": "hermes-model",
        "HERMES_MODEL_API_KEY": MODEL_KEY,
    }
    values.update(extra)
    return values


def _skill(tmp_path: Path) -> None:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("---\nname: demo\nversion: 0.1.0\n---\n# Purpose\nDemo\n", encoding="utf-8")


class _Model:
    model = "hermes-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return "ready"


class _Jev:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        return JevResult(model="jev-1.13.0", answers=self.answers, usage={})


class _Chroma:
    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        assert limit == 10
        return [{"id": "note-1", "text": "tuesday meeting", "distance": 0.25}]


def _agent(tmp_path: Path, **extra: str) -> HermesAgent:
    _skill(tmp_path)
    settings = load_settings(_base(tmp_path, **extra))
    return HermesAgent(settings, model_client=_Model(), chroma_client=_Chroma())


class _QueueJev:
    """Fails closed if the tool-call pack is invoked; serves memory-write answers in order."""

    def __init__(self, memory_answers: list[dict[str, object]]) -> None:
        self.memory_answers = list(memory_answers)
        self.tool_calls = 0
        self.memory_calls = 0

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        if "needs_tool" in questions:
            self.tool_calls += 1
            raise AssertionError("MCP memory trio must not run the tool-call pack")
        self.memory_calls += 1
        return JevResult(
            model="jev-1.13.0",
            answers=self.memory_answers[self.memory_calls - 1],
            usage={},
        )


def _memory_kept(kind: str = "fact", worth: float = 0.8) -> dict[str, object]:
    return {
        "worth": {"type": "noul", "noul": worth},
        "kind": {
            "type": "choice",
            "choice": kind,
            "probabilities": {kind: 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }


def _soft_agent(tmp_path: Path, jev: object) -> HermesAgent:
    _skill(tmp_path)
    settings = load_settings(
        _base(
            tmp_path,
            HERMES_MCP_ENABLED="on",
            HERMES_JEV_MODE="soft",
            HERMES_JEV_API_KEY="0123456789abcdef",
        )
    )
    return HermesAgent(
        settings,
        model_client=_Model(),
        chroma_client=_Chroma(),
        jev_client=jev,
    )


def _app(tmp_path: Path, mcp_limit: int | None = None, **extra: str):
    from api.app import create_app

    _skill(tmp_path)
    settings = load_settings(_base(tmp_path, **extra))
    return create_app(
        settings,
        chroma_reachable=lambda: True,
        chroma_client=_Chroma(),
        model_client=_Model(),
        mcp_limit=mcp_limit,
    )


def _rpc(method: str, params: dict[str, object], request_id: int = 1) -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _post(client: TestClient, body: dict[str, object], token: str | None = TOKEN):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/mcp", headers=headers, json=body)


def test_mcp_defaults_off_and_requires_a_token_when_on(tmp_path: Path) -> None:
    off = load_settings(_base(tmp_path))
    assert off.mcp_enabled is False
    assert off.mcp_allowed_hosts == ()
    with pytest.raises(SettingsError, match="HERMES_API_TOKEN"):
        load_settings(_base(tmp_path, HERMES_API_TOKEN="", HERMES_MCP_ENABLED="on"))
    with pytest.raises(SettingsError, match="HERMES_MCP_ENABLED"):
        load_settings(_base(tmp_path, HERMES_MCP_ENABLED="true"))
    with pytest.raises(SettingsError, match="HERMES_MCP_ALLOWED_HOSTS"):
        load_settings(_base(tmp_path, HERMES_MCP_ALLOWED_HOSTS="https://hermes.example"))


def test_disabled_mcp_is_404_and_health_stays_secret_free(tmp_path: Path) -> None:
    from api.app import create_app

    app = create_app(load_settings(_base(tmp_path)), chroma_reachable=lambda: True)
    client = TestClient(app)
    health = client.get("/health")
    missing = client.post("/mcp", json=_rpc("tools/list", {}))
    assert health.status_code == 200
    assert health.json()["mcp"]["enabled"] is False
    assert TOKEN not in health.text
    assert MODEL_KEY not in health.text
    assert missing.status_code == 404


def test_enabled_mcp_rejects_a_missing_bearer_and_lists_seven_tools(tmp_path: Path) -> None:
    app = _app(tmp_path, HERMES_MCP_ENABLED="on")
    with TestClient(app) as client:
        health = client.get("/health")
        denied = _post(client, _rpc("tools/list", {}), token=None)
        wrong = _post(client, _rpc("tools/list", {}), token="0" * 16)
        listed = _post(client, _rpc("tools/list", {}))
    assert health.json()["mcp"]["enabled"] is True
    assert TOKEN not in health.text
    assert denied.status_code == 401
    assert wrong.status_code == 401
    assert listed.status_code == 200
    names = _tool_names(listed.json())
    assert names == [
        "complete",
        "list_skills",
        "recall",
        "remember",
        "search_documents",
        "search_memory",
        "suggest_skill",
    ]
    assert "delete_memory" not in names
    assert "delegate_to_grok" not in names
    assert set(names) == set(MCP_TOOLS)


def test_mcp_without_trailing_slash_does_not_redirect(tmp_path: Path) -> None:
    """Bare /mcp must not 307 to /mcp/; redirects drop Authorization on some clients."""
    app = _app(tmp_path, HERMES_MCP_ENABLED="on")
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {TOKEN}",
    }
    body = _rpc("tools/list", {})
    with TestClient(app, follow_redirects=False) as client:
        bare = client.post("/mcp", headers=headers, json=body)
        slashed = client.post("/mcp/", headers=headers, json=body)
    assert bare.status_code != 307
    assert bare.status_code == 200
    assert slashed.status_code == 200
    assert _tool_names(bare.json()) == _tool_names(slashed.json())


def test_soft_mcp_memory_trio_skips_tool_call_pack(tmp_path: Path) -> None:
    jev = _QueueJev([_memory_kept()])
    agent = _soft_agent(tmp_path, jev)
    assert "demo 0.1.0" in call_tool(agent, "list_skills", {})
    assert call_tool(agent, "remember", {"key": "note", "value": "durable fact for tomorrow"}) == "stored"
    assert call_tool(agent, "recall", {"key": "note"}) == "durable fact for tomorrow"
    assert jev.tool_calls == 0
    assert jev.memory_calls == 1


def test_soft_mcp_remember_still_skips_chatter(tmp_path: Path) -> None:
    jev = _QueueJev([_memory_kept(kind="none", worth=0.9)])
    agent = _soft_agent(tmp_path, jev)
    assert call_tool(agent, "remember", {"key": "ping", "value": "ok"}) == "skipped"
    assert call_tool(agent, "recall", {"key": "ping"}) == MISSING_TEXT
    assert jev.tool_calls == 0
    assert jev.memory_calls == 1


def test_tools_call_the_agent_and_refuse_unknown_arguments(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    assert "demo 0.1.0" in call_tool(agent, "list_skills", {})
    assert call_tool(agent, "delete_memory", {"key": "note"}) == REFUSED_TEXT
    assert call_tool(agent, "delegate_to_grok", {"task": "read the notes"}) == REFUSED_TEXT
    assert call_tool(agent, "recall", {"key": "note", "extra": "no"}) == ARGUMENTS_TEXT
    assert call_tool(agent, "remember", {"key": "note", "value": "kept"}) == "stored"
    assert call_tool(agent, "recall", {"key": "note"}) == "kept"
    assert "note-1" in call_tool(agent, "search_documents", {"q": "tuesday"})
    assert call_tool(agent, "search_documents", {"q": "tuesday", "extra": "no"}) == ARGUMENTS_TEXT

    app = _app(tmp_path, HERMES_MCP_ENABLED="on")
    with TestClient(app) as client:
        skills = _post(client, _rpc("tools/call", {"name": "list_skills", "arguments": {}}))
        extra = _post(
            client,
            _rpc("tools/call", {"name": "recall", "arguments": {"key": "note", "extra": "no"}}),
        )
        found = _post(
            client,
            _rpc("tools/call", {"name": "search_documents", "arguments": {"q": "tuesday"}}),
        )
        done = _post(
            client,
            _rpc("tools/call", {"name": "complete", "arguments": {"prompt": "status"}}),
        )
    assert skills.status_code == 200
    assert "demo 0.1.0" in skills.text
    assert extra.json()["result"]["isError"] is True
    assert "extra_forbidden" in extra.text
    assert "note-1" in found.text
    assert "ready" in done.text


def test_suggest_skill_mode_off_returns_unavailable_json(tmp_path: Path) -> None:
    import json

    agent = _agent(tmp_path)  # jev mode defaults off
    raw = call_tool(
        agent,
        "suggest_skill",
        {
            "request": "deploy",
            "skills": [{"name": "deploy", "description": "Promote Hermes."}],
        },
    )
    payload = json.loads(raw)
    assert payload["available"] is False
    assert payload["line"] == ""


def test_complete_still_withholds_a_guarded_reply(tmp_path: Path) -> None:
    _skill(tmp_path)
    settings = load_settings(
        _base(
            tmp_path,
            HERMES_MCP_ENABLED="on",
            HERMES_JEV_MODE="soft",
            HERMES_JEV_API_KEY="0123456789abcdef",
        )
    )
    review = {
        "jailbreak": {"type": "noul", "noul": 0.01},
        "credential_harvest": {"type": "noul", "noul": 0.01},
        "self_harm": {"type": "noul", "noul": 0.5},
        "blast_radius": {"type": "score", "score": 0.1},
    }
    model = _Model()
    agent = HermesAgent(settings, model_client=model, jev_client=_Jev(review), chroma_client=_Chroma())
    assert call_tool(agent, "complete", {"prompt": "status"}) == REVIEW_TEXT
    assert model.prompts == []


def test_request_cap_refuses_without_queueing(tmp_path: Path) -> None:
    app = _app(tmp_path, mcp_limit=2, HERMES_MCP_ENABLED="on")
    with TestClient(app) as client:
        first = _post(client, _rpc("tools/list", {}), token=None)
        second = _post(client, _rpc("tools/list", {}), token=None)
        third = _post(client, _rpc("tools/list", {}))
    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert third.json()["detail"] == LIMIT_TEXT
    assert MAX_MCP_REQUESTS == 60


def test_unlisted_host_is_refused(tmp_path: Path) -> None:
    refused_app = _app(tmp_path, HERMES_MCP_ENABLED="on")
    with TestClient(refused_app, base_url="http://evil.example") as client:
        refused = _post(client, _rpc("tools/list", {}))
    allowed_app = _app(tmp_path, HERMES_MCP_ENABLED="on", HERMES_MCP_ALLOWED_HOSTS="hermes.example")
    with TestClient(allowed_app, base_url="http://hermes.example") as client:
        allowed = _post(client, _rpc("tools/list", {}))
    assert refused.status_code == 421
    assert allowed.status_code == 200


def _tool_names(body: dict[str, object]) -> list[str]:
    result = body["result"]
    assert isinstance(result, dict)
    tools = result["tools"]
    assert isinstance(tools, list)
    return sorted(str(tool["name"]) for tool in tools)
