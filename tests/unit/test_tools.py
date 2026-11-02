"""The tool runner executes an allowlist. Shadow only logs the tool-call judgment."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.decisions.tool_gate import TOOL_CRITERIA, WHICH, judge
from agent.decisions.tool_gate import HARM_LEVEL, NEEDS_LABEL, UNSURE
from agent.tools import TOOL_ARGUMENTS
from agent.tools import (
    ARGUMENTS_TEXT,
    ASK_TEXT,
    GATE_TEXT,
    MAX_STEPS,
    MISSING_TEXT,
    OFF_TEXT,
    REJECTED_TEXT,
    TASK_TEXT,
    UNKNOWN_TEXT,
    ToolCall,
)
from services.grok import GrokError, MAX_TASK_CHARS
from api.app import create_app
from services.chroma import ChromaClient
from services.jev import JevError, JevResult
from utils.settings import load_settings


class _Jev:
    def __init__(self, responses: list[dict[str, object] | Exception] | None = None) -> None:
        self.responses = responses or []
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        if "looping" in questions:
            return JevResult(
                model="jev-1.13.0",
                answers={
                    "looping": {"type": "noul", "noul": 0.01},
                    "progress": {"type": "score", "score": 1.0},
                    "complete": {"type": "noul", "noul": 0.01},
                },
                usage={},
            )
        scripted = [call for call in self.calls if "looping" not in call[1]]
        if not self.responses:
            return JevResult(model="jev-1.13.0", answers={}, usage={})
        item = self.responses[len(scripted) - 1]
        if isinstance(item, Exception):
            raise item
        return JevResult(model="jev-1.13.0", answers=item, usage={})


def _judgment(
    choice: str = "list_skills",
    calls: int = 1,
    needs: float = 0.8,
    safe: float = 0.2,
    blast: float = 0.4,
) -> dict[str, object]:
    answers: dict[str, object] = {
        "needs_tool": {"type": "noul", "noul": needs},
        "tool": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }
    for index in range(calls):
        answers[f"safe::{index}"] = {"type": "noul", "noul": safe}
        answers[f"blast::{index}"] = {"type": "score", "score": blast}
    return answers


def _agent(
    tmp_path: Path,
    jev: object | None = None,
    mode: str = "off",
    extra: dict[str, str] | None = None,
    grok: object | None = None,
) -> HermesAgent:
    skills = tmp_path / "skills" / "demo"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: demo\nversion: 0.1.0\n---\n# Purpose\nDemo\n",
        encoding="utf-8",
    )
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        "HERMES_JEV_MODE": mode,
    }
    if mode != "off":
        values["HERMES_JEV_API_KEY"] = "fedcba9876543210"
    if extra:
        values.update(extra)
    settings = load_settings(values)
    return HermesAgent(
        settings,
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        jev_client=jev,
        grok_client=grok,
    )


def test_recall_and_list_skills_run_in_order(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    agent.remember("boot", "started")
    results = agent.run_tools(
        [
            ToolCall("remember", {"key": "note", "value": "value-secret-7c2e"}),
            ToolCall("recall", {"key": "note"}),
            ToolCall("list_skills", {}),
        ]
    )
    assert [result.status for result in results] == ["ran", "ran", "ran"]
    assert results[1].output == "value-secret-7c2e"
    assert results[2].output == "demo 0.1.0"
    assert agent.recall("note") == "value-secret-7c2e"


def test_unknown_and_extra_arguments_are_refused(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    results = agent.run_tools(
        [
            ToolCall("shell", {"command": "rm"}),
            ToolCall("recall", {"key": "boot", "extra": "nope"}),
            ToolCall("recall", {"key": "../secret"}),
        ]
    )
    assert results[0].status == "refused"
    assert results[0].output == UNKNOWN_TEXT
    assert results[1].output == ARGUMENTS_TEXT
    assert results[2].output == ARGUMENTS_TEXT
    with pytest.raises(FileNotFoundError):
        agent.recall("boot")


def test_delete_memory_asks_a_person_and_keeps_the_file(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    agent.remember("boot", "started")
    results = agent.run_tools([ToolCall("delete_memory", {"key": "boot"})])
    assert results[0].status == "ask_person"
    assert results[0].output == ASK_TEXT
    assert agent.recall("boot") == "started"


def test_a_missing_record_is_a_ran_result(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    results = agent.run_tools([ToolCall("recall", {"key": "missing"})])
    assert results[0].status == "ran"
    assert results[0].output == MISSING_TEXT


def test_step_limit_runs_nothing(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
    calls = [ToolCall("remember", {"key": "boot", "value": "started"})] * (MAX_STEPS + 1)
    with pytest.raises(ValueError, match="limited"):
        agent.run_tools(calls)
    with pytest.raises(FileNotFoundError):
        agent.recall("boot")


def test_mode_off_does_not_call_jev(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev()
    agent = _agent(tmp_path, jev)
    with caplog.at_level("INFO", logger="hermes"):
        agent.run_tools([ToolCall("remember", {"key": "boot", "value": "value-secret-7c2e"})])
    assert jev.calls == []
    assert "tools.run name=remember status=ran" in caplog.text
    assert "value-secret-7c2e" not in caplog.text


def test_one_request_keeps_argument_values_out_of_the_questions() -> None:
    value = "value-secret-7c2e"
    jev = _Jev([_judgment("remember")])
    result = judge(jev, [ToolCall("remember", {"key": "boot", "value": value})])
    assert result.choice == "remember"
    assert result.reason == "ok"
    state, questions = jev.calls[0]
    assert state["calls"][0]["arguments"]["value"] == value
    dumped = json.dumps(questions)
    assert value not in dumped
    assert questions["tool"]["instructions"] == WHICH
    assert questions["tool"]["criteria"]["none"]
    assert set(TOOL_CRITERIA) == set(TOOL_ARGUMENTS)
    assert set(questions["tool"]["criteria"]) == {"none", *TOOL_CRITERIA}


def test_shadow_logs_the_choice_and_still_runs(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([_judgment("list_skills", calls=2)])
    agent = _agent(tmp_path, jev, "shadow")
    agent.memory.write("boot", "started")
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools(
            [
                ToolCall("list_skills", {}),
                ToolCall("delete_memory", {"key": "boot"}),
            ]
        )
    assert [result.status for result in results] == ["ran", "ask_person"]
    assert results[0].output == "demo 0.1.0"
    assert agent.recall("boot") == "started"
    assert len(jev.calls) == 2
    assert "pack=tool-call" in caplog.text
    assert "tool=list_skills" in caplog.text
    assert "calls=list_skills,delete_memory" in caplog.text
    assert "statuses=ran,ask_person" in caplog.text
    assert "effective=advise" in caplog.text
    assert "enforced=false" in caplog.text
    decision = next(line for line in caplog.text.splitlines() if "jev.decision" in line)
    assert "boot" not in decision


def test_soft_refuses_when_jev_picks_none(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([_judgment("none", safe=0.9)])
    agent = _agent(tmp_path, jev, "soft")
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools([ToolCall("list_skills", {})])
    assert results[0].status == "refused"
    assert results[0].output == GATE_TEXT
    assert "reason=none" in caplog.text
    assert "proposed=refuse" in caplog.text
    assert "effective=refuse" in caplog.text
    assert "enforced=true" in caplog.text
    assert "statuses=refused" in caplog.text


def test_soft_runs_above_unsure_and_holds_the_middle_band(tmp_path: Path) -> None:
    jev = _Jev(
        [
            _judgment(safe=UNSURE, blast=0.1),
            _judgment(safe=0.9, blast=float(HARM_LEVEL)),
            _judgment(needs=NEEDS_LABEL - 0.01, safe=0.9, blast=0.1),
            _judgment(needs=NEEDS_LABEL, safe=UNSURE + 0.01, blast=float(HARM_LEVEL) - 0.1),
            _judgment("recall", calls=2, safe=0.9, blast=0.1),
        ]
    )
    agent = _agent(tmp_path, jev, "soft")
    unsure = agent.run_tools([ToolCall("list_skills", {})])
    harm = agent.run_tools([ToolCall("list_skills", {})])
    unneeded = agent.run_tools([ToolCall("list_skills", {})])
    clear = agent.run_tools([ToolCall("list_skills", {})])
    mixed = agent.run_tools(
        [ToolCall("recall", {"key": "boot"}), ToolCall("list_skills", {})]
    )
    assert unsure[0].status == "ask_person"
    assert harm[0].status == "ask_person"
    assert unneeded[0].status == "refused"
    assert unneeded[0].output == GATE_TEXT
    assert clear[0].status == "ran"
    assert clear[0].output == "demo 0.1.0"
    assert [result.status for result in mixed] == ["ran", "refused"]
    assert mixed[0].output == MISSING_TEXT


def test_soft_does_not_store_a_held_memory_write(tmp_path: Path) -> None:
    kept = {
        "worth": {"type": "noul", "noul": 0.8},
        "kind": {
            "type": "choice",
            "choice": "fact",
            "probabilities": {"fact": 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }
    jev = _Jev(
        [
            _judgment("remember", safe=UNSURE, blast=0.1),
            _judgment("remember", safe=0.9, blast=0.1),
            kept,
        ]
    )
    agent = _agent(tmp_path, jev, "soft")
    held = agent.run_tools([ToolCall("remember", {"key": "boot", "value": "value-secret-7c2e"})])
    assert held[0].status == "ask_person"
    with pytest.raises(FileNotFoundError):
        agent.recall("boot")
    stored = agent.run_tools([ToolCall("remember", {"key": "boot", "value": "kept"})])
    assert stored[0].output == "stored"
    assert agent.recall("boot") == "kept"


def test_soft_jev_error_asks_a_person_instead_of_running(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _agent(tmp_path, jev, "soft")
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools([ToolCall("list_skills", {})])
    assert results[0].status == "ask_person"
    assert results[0].output == ASK_TEXT
    assert "reason=jev_error" in caplog.text
    assert "effective=ask_person" in caplog.text
    assert "enforced=true" in caplog.text


def test_soft_cannot_override_an_irreversible_tool(tmp_path: Path) -> None:
    jev = _Jev([_judgment("delete_memory", safe=0.99, blast=0.1)])
    agent = _agent(tmp_path, jev, "soft")
    agent.memory.write("boot", "started")
    results = agent.run_tools([ToolCall("delete_memory", {"key": "boot"})])
    assert results[0].status == "ask_person"
    assert results[0].output == ASK_TEXT
    assert agent.recall("boot") == "started"


def test_jev_error_still_runs_the_allowlist(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([JevError("Jev request failed", 429)])
    agent = _agent(tmp_path, jev, "shadow")
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools([ToolCall("list_skills", {})])
    assert results[0].status == "ran"
    assert "reason=jev_error" in caplog.text
    assert "proposed=ask_person" in caplog.text
    assert "effective=advise" in caplog.text


def test_step_limit_does_not_call_jev(tmp_path: Path) -> None:
    jev = _Jev([_judgment()])
    agent = _agent(tmp_path, jev, "shadow")
    calls = [ToolCall("list_skills", {})] * (MAX_STEPS + 1)
    with pytest.raises(ValueError, match="limited"):
        agent.run_tools(calls)
    assert jev.calls == []


def test_tools_route_requires_the_credential_and_hides_arguments(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "HERMES_ENV": "test",
            "CHROMA_HOST": "chromadb",
            "HERMES_API_TOKEN": "fedcba9876543210",
            "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
            "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        }
    )
    client = TestClient(
        create_app(
            settings,
            chroma_reachable=lambda: True,
            chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        )
    )
    body = {"calls": [{"name": "recall", "arguments": {"key": "boot"}}]}
    denied = client.post("/tools", json=body)
    assert denied.status_code == 401
    allowed = client.post("/tools", json=body, headers={"Authorization": "Bearer fedcba9876543210"})
    assert allowed.status_code == 200
    assert allowed.json()["results"][0]["output"] == MISSING_TEXT
    too_many = client.post(
        "/tools",
        json={"calls": [{"name": "list_skills", "arguments": {}}] * (MAX_STEPS + 1)},
        headers={"Authorization": "Bearer fedcba9876543210"},
    )
    assert too_many.status_code == 400


class _Boom:
    def send(self, task: str) -> str:
        raise AssertionError(task)


class _Script:
    def __init__(self, result: str | Exception = "abc123") -> None:
        self.result = result
        self.tasks: list[str] = []

    def send(self, task: str) -> str:
        self.tasks.append(task)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


_GROK_ON = {
    "HERMES_GROK_HANDOFF": "on",
    "HERMES_GROK_WEBHOOK_URL": "https://agent.example/v1/channels/hermes/task",
    "HERMES_GROK_ALIAS_TOKEN": "0123456789abcdef",
    "HERMES_GROK_HANDOFF_SECRET": "fedcba9876543210",
}


def test_grok_handoff_off_and_ask_do_not_post(tmp_path: Path) -> None:
    off = _agent(tmp_path / "off", grok=_Boom())
    asked = _agent(tmp_path / "ask", extra={"HERMES_GROK_HANDOFF": "ask"}, grok=_Boom())
    off_result = off.run_tools([ToolCall("delegate_to_grok", {"task": "read the notes"})])
    ask_result = asked.run_tools([ToolCall("delegate_to_grok", {"task": "read the notes"})])
    assert off_result[0].status == "refused"
    assert off_result[0].output == OFF_TEXT
    assert ask_result[0].status == "ask_person"
    assert ask_result[0].output == ASK_TEXT


def test_grok_handoff_on_posts_the_task_and_returns_the_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    script = _Script()
    agent = _agent(tmp_path, extra=_GROK_ON, grok=script)
    task = "read the notes"
    with caplog.at_level("INFO", logger="hermes"):
        results = agent.run_tools([ToolCall("delegate_to_grok", {"task": task})])
    assert results[0].status == "ran"
    assert results[0].output == "abc123"
    assert script.tasks == [task]
    assert "id=abc123" in caplog.text
    assert task not in caplog.text
    assert "0123456789abcdef" not in caplog.text


def test_grok_handoff_refuses_a_long_task_and_a_rejected_post(tmp_path: Path) -> None:
    script = _Script(GrokError())
    agent = _agent(tmp_path, extra=_GROK_ON, grok=script)
    long = agent.run_tools([ToolCall("delegate_to_grok", {"task": "x" * (MAX_TASK_CHARS + 1)})])
    empty = agent.run_tools([ToolCall("delegate_to_grok", {"task": "   "})])
    extra = agent.run_tools([ToolCall("delegate_to_grok", {"task": "read", "note": "secret"})])
    rejected = agent.run_tools([ToolCall("delegate_to_grok", {"task": "read the notes"})])
    assert long[0].output == TASK_TEXT
    assert empty[0].output == TASK_TEXT
    assert extra[0].output == ARGUMENTS_TEXT
    assert rejected[0].output == REJECTED_TEXT
    assert script.tasks == ["read the notes"]


def test_soft_mode_can_hold_a_grok_handoff(tmp_path: Path) -> None:
    script = _Script()
    jev = _Jev([_judgment("none", safe=0.9)])
    agent = _agent(tmp_path, jev, "soft", extra=_GROK_ON, grok=script)
    results = agent.run_tools([ToolCall("delegate_to_grok", {"task": "read the notes"})])
    assert results[0].status == "refused"
    assert results[0].output == GATE_TEXT
    assert script.tasks == []
