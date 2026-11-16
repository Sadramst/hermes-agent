"""Allowlisted tool runner and /tools route contract."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.core import HermesAgent
from agent.tools import (
    ARGUMENTS_TEXT,
    ASK_TEXT,
    MAX_STEPS,
    MISSING_TEXT,
    UNKNOWN_TEXT,
    ToolCall,
)
from api.app import create_app
from services.chroma import ChromaClient
from utils.settings import load_settings


def _agent(tmp_path: Path, extra: dict[str, str] | None = None) -> HermesAgent:
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
    }
    if extra:
        values.update(extra)
    settings = load_settings(values)
    return HermesAgent(
        settings,
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
    )


def test_recall_remember_and_list_skills_run_in_order(tmp_path: Path) -> None:
    agent = _agent(tmp_path)
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


def test_tool_logging_omits_argument_values(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    agent = _agent(tmp_path)
    with caplog.at_level("INFO", logger="hermes"):
        agent.run_tools([ToolCall("remember", {"key": "boot", "value": "value-secret-7c2e"})])
    assert "tools.run name=remember status=ran" in caplog.text
    assert "value-secret-7c2e" not in caplog.text


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
