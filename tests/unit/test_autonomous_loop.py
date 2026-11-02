"""Autonomous multi-step tool-calling loop, expanded tools, and /agent/run contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.tools import ToolCall
from api.app import create_app
from cli.main import main as cli_main
from services.chroma import ChromaClient
from services.model import ModelClient, ModelToolCall, ModelTurn
from utils.settings import load_settings

TOKEN = "fedcba9876543210"
MODEL_KEY = "0123456789abcdef"


class _ScriptedChatModel:
    """Fake model client that scripts multi-step tool calls followed by a final answer."""

    model = "google/gemini-2.5-flash"

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = list(turns)
        self.calls: list[tuple[list[dict[str, object]], list[dict[str, object]] | None]] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        return "single-turn"

    def chat(
        self,
        messages: list[dict[str, object]],
        *,
        tools: list[dict[str, object]] | None = None,
        model: str | None = None,
    ) -> ModelTurn:
        self.calls.append((list(messages), tools))
        return self.turns[len(self.calls) - 1]


class _FakeChroma:
    def __init__(self) -> None:
        self.saved: dict[str, str] = {}

    def heartbeat(self) -> bool:
        return True

    def upsert_chunks(self, ids: list[str], texts: list[str], embeddings: list, metadatas: list) -> None:
        for cid, text in zip(ids, texts):
            self.saved[cid] = text

    def delete_source(self, field: str, value: str) -> None:
        return None

    def source_metadatas(self, field: str, value: str) -> list[dict[str, object]]:
        return []

    def query_documents(self, embedding: list[float], limit: int) -> list[dict[str, object]]:
        return [
            {"id": cid, "text": text, "distance": 0.1}
            for cid, text in list(self.saved.items())[:limit]
        ]


def _settings(tmp_path: Path, token: str = "") -> object:
    skill_dir = tmp_path / "skills" / "deploy-guide"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: deploy-guide\nversion: 1.0.0\n---\n# Purpose\nDeploy Hermes on Ubuntu.\n\n# Steps\nRun deploy.sh prod.\n",
        encoding="utf-8",
    )
    return load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "CHROMA_PORT": "8000",
            "HERMES_API_TOKEN": token,
            "HERMES_MODEL_BASE_URL": "https://openrouter.ai/api/v1",
            "HERMES_MODEL_NAME": "google/gemini-2.5-flash",
            "HERMES_MODEL_API_KEY": MODEL_KEY,
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        }
    )


def test_model_client_chat_parses_tool_calls_and_sends_tools_schema() -> None:
    seen: list[dict[str, object]] = []

    class _Resp:
        status = 200

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "remember",
                                            "arguments": '{"key": "server-ip", "value": "10.0.0.5"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ).encode("utf-8")

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    def opener(request, timeout):  # noqa: ANN001
        seen.append(json.loads(request.data or b"{}"))
        return _Resp()

    client = ModelClient(
        "https://openrouter.ai/api/v1",
        "google/gemini-2.5-flash",
        MODEL_KEY,
        opener=opener,
    )
    turn = client.chat(
        [{"role": "user", "content": "Save server IP"}],
        tools=[{"type": "function", "function": {"name": "remember"}}],
    )
    assert turn.content == ""
    assert turn.tool_calls == [
        ModelToolCall(id="call_1", name="remember", arguments={"key": "server-ip", "value": "10.0.0.5"})
    ]
    assert seen[0]["tool_choice"] == "auto"
    assert len(seen[0]["tools"]) == 1  # type: ignore[arg-type]


def test_autonomous_loop_executes_multiple_steps_and_synthesizes_final_answer(tmp_path: Path) -> None:
    turns = [
        ModelTurn(
            content="",
            tool_calls=[
                ModelToolCall(id="c1", name="remember", arguments={"key": "owner", "value": "Sadramst"}),
                ModelToolCall(id="c2", name="read_skill", arguments={"name": "deploy-guide"}),
            ],
        ),
        ModelTurn(
            content="",
            tool_calls=[
                ModelToolCall(id="c3", name="search_memory", arguments={"q": "Sadramst"}),
            ],
        ),
        ModelTurn(
            content="Owner is Sadramst and deployment uses deploy.sh prod.",
            tool_calls=[],
        ),
    ]
    model = _ScriptedChatModel(turns)
    chroma = _FakeChroma()
    agent = HermesAgent(_settings(tmp_path), chroma_client=chroma, model_client=model)  # type: ignore[arg-type]

    result = agent.run_agent("Store owner Sadramst, check the deploy skill, and confirm.")
    assert result["text"] == "Owner is Sadramst and deployment uses deploy.sh prod."
    assert result["model"] == "google/gemini-2.5-flash"
    steps = result["steps"]
    assert isinstance(steps, list)
    assert [s["name"] for s in steps] == ["remember", "read_skill", "search_memory"]
    assert [s["status"] for s in steps] == ["ran", "ran", "ran"]
    assert "Run deploy.sh prod." in steps[1]["output"]
    assert "Sadramst" in steps[2]["output"]
    assert agent.recall("owner") == "Sadramst"


def test_autonomous_loop_stops_early_on_irreversible_tool_and_synthesizes(tmp_path: Path) -> None:
    turns = [
        ModelTurn(
            content="",
            tool_calls=[
                ModelToolCall(id="c1", name="delete_memory", arguments={"key": "owner"}),
            ],
        ),
        ModelTurn(
            content="Deletion requires human confirmation.",
            tool_calls=[],
        ),
    ]
    model = _ScriptedChatModel(turns)
    agent = HermesAgent(_settings(tmp_path), chroma_client=_FakeChroma(), model_client=model)  # type: ignore[arg-type]
    agent.remember("owner", "Sadramst")

    result = agent.run_agent("Delete owner memory")
    assert result["text"] == "Deletion requires human confirmation."
    assert result["steps"] == [
        {
            "step": 1,
            "name": "delete_memory",
            "status": "ask_person",
            "output": "This tool needs a person before it can run.",
        }
    ]
    assert agent.recall("owner") == "Sadramst"


def test_expanded_tools_save_and_search_documents_and_read_skill(tmp_path: Path) -> None:
    chroma = _FakeChroma()
    agent = HermesAgent(_settings(tmp_path), chroma_client=chroma)  # type: ignore[arg-type]
    results = agent.run_tools(
        [
            ToolCall("save_document", {"id": "runbook", "text": "Use port 8569 in production."}),
            ToolCall("search_documents", {"q": "port 8569"}),
            ToolCall("read_skill", {"name": "deploy-guide"}),
            ToolCall("read_skill", {"name": "unknown-skill"}),
        ]
    )
    assert [r.status for r in results] == ["ran", "ran", "ran", "ran"]
    assert "saved id=runbook" in results[0].output
    assert "[runbook::0000]" in results[1].output
    assert "Use port 8569 in production." in results[1].output
    assert "Run deploy.sh prod." in results[2].output
    assert results[3].output == "No skill is loaded with that name."


def test_agent_run_and_autonomous_completions_http_routes(tmp_path: Path) -> None:
    turns = [
        ModelTurn(
            content="",
            tool_calls=[ModelToolCall(id="c1", name="list_skills", arguments={})],
        ),
        ModelTurn(content="Loaded skill: deploy-guide 1.0.0", tool_calls=[]),
        ModelTurn(content="Direct autonomous completion", tool_calls=[]),
    ]
    model = _ScriptedChatModel(turns)
    app = create_app(
        _settings(tmp_path, TOKEN),  # type: ignore[arg-type]
        chroma_reachable=lambda: True,
        chroma_client=_FakeChroma(),  # type: ignore[arg-type]
        model_client=model,  # type: ignore[arg-type]
    )
    client = TestClient(app)

    denied = client.post("/agent/run", json={"prompt": "check skills"})
    assert denied.status_code == 401

    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = client.post("/agent/run", json={"prompt": "check skills", "max_steps": 3}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Loaded skill: deploy-guide 1.0.0"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["name"] == "list_skills"

    comp = client.post(
        "/completions",
        json={"prompt": "check skills", "autonomous": True, "max_steps": 2},
        headers=headers,
    )
    assert comp.status_code == 200
    assert comp.json()["text"] == "Direct autonomous completion"
    assert comp.json()["steps"] == []

    bad_steps = client.post("/agent/run", json={"prompt": "hi", "max_steps": 99}, headers=headers)
    assert bad_steps.status_code == 400


def test_cli_run_subcommand_invokes_autonomous_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("HERMES_ENV", "test")
    monkeypatch.setenv("CHROMA_HOST", "chromadb")
    monkeypatch.setenv("HERMES_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("HERMES_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setattr(
        HermesAgent,
        "run_agent",
        lambda self, prompt, max_steps=4: {"text": f"solved: {prompt}", "model": "test", "steps": []},
    )
    code = cli_main(["run", "check stack", "--max-steps", "2"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "solved: check stack"
