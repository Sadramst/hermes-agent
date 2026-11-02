"""Supervisors log looping, progress, and completeness.

Soft mode stops tool calls that follow a looping judgment. The completion
text stays as the model wrote it.
"""

import json
from pathlib import Path

import pytest

from agent.core import HermesAgent
from agent.decisions.guardrails import BLOCK_TEXT
from agent.decisions.supervisor import (
    COMPLETE,
    LOOPING,
    PROGRESS_LEVEL,
    STOP_TEXT,
    UNSURE,
    judge,
    label_step,
)
from agent.tools import ToolCall
from services.chroma import ChromaClient
from services.jev import JevError, JevResult
from utils.settings import load_settings


class _Model:
    model = "hermes-model"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        return "ready"


class _Jev:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        item = self.responses[len(self.calls) - 1]
        if isinstance(item, Exception):
            raise item
        return JevResult(model="jev-1.13.0", answers=item, usage={})


def _quiet(looping: float = 0.01, progress: float = 1.0, done: float = 0.01) -> dict[str, object]:
    return {
        "looping": {"type": "noul", "noul": looping},
        "progress": {"type": "score", "score": progress},
        "complete": {"type": "noul", "noul": done},
    }


def _guards() -> dict[str, object]:
    return {
        "jailbreak": {"type": "noul", "noul": 0.01},
        "credential_harvest": {"type": "noul", "noul": 0.01},
        "self_harm": {"type": "noul", "noul": 0.01},
        "blast_radius": {"type": "score", "score": 0.1},
    }


def _tier() -> dict[str, object]:
    return {
        "tier": {
            "type": "choice",
            "choice": "frontier",
            "probabilities": {"frontier": 0.8, "none": 0.2},
            "confidence": 0.8,
        }
    }


def _block() -> dict[str, object]:
    screened = _guards()
    screened["blast_radius"] = {"type": "score", "score": 3.0}
    return screened


def _wide() -> dict[str, object]:
    return {
        "which": {
            "type": "choice",
            "choice": "alpha",
            "probabilities": {"alpha": 0.7, "none": 0.3},
            "confidence": 0.8,
        },
        "gate::acts_on_user_system": {"type": "noul", "noul": 0.1},
        "gate::would_follow_documented_procedure": {"type": "noul", "noul": 0.1},
        "gate::prose_suffices": {"type": "noul", "noul": 0.9},
    }


def _agent(tmp_path: Path, mode: str, jev: object, model: object | None = None) -> HermesAgent:
    skills = tmp_path / "skills" / "alpha"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: alpha\nversion: 1.0.0\n---\n# Purpose\nAlpha skill\n",
        encoding="utf-8",
    )
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        "HERMES_MODEL_BASE_URL": "https://models.example/v1",
        "HERMES_MODEL_NAME": "hermes-model",
        "HERMES_MODEL_API_KEY": "0123456789abcdef",
        "HERMES_JEV_MODE": mode,
    }
    if mode != "off":
        values["HERMES_JEV_API_KEY"] = "fedcba9876543210"
    return HermesAgent(
        load_settings(values),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
        jev_client=jev,
    )


def test_labels_use_the_unsure_line_and_the_progress_level() -> None:
    assert label_step(_quiet(looping=UNSURE, done=0.9, progress=3))[0] == "looping"
    assert label_step(_quiet(done=UNSURE, progress=float(PROGRESS_LEVEL)))[0] == "complete"
    assert label_step(_quiet(done=0.9, progress=float(PROGRESS_LEVEL) - 0.1))[0] == "continue"


def test_questions_omit_evidence_text() -> None:
    secret = "value-secret-7c2e"
    jev = _Jev([_quiet(done=0.9, progress=2.4)])
    result = judge(
        jev,
        [{"id": "0", "name": "recall", "status": "ran"}],
        [{"id": "0", "text": secret}],
    )
    assert result.reason == "complete"
    state, questions = jev.calls[0]
    assert state["evidence"][0]["text"] == secret
    dumped = json.dumps(questions)
    assert secret not in dumped
    assert "ready" not in dumped
    assert questions["looping"]["instructions"] == LOOPING
    assert questions["complete"]["instructions"] == COMPLETE


def test_shadow_logs_a_tool_loop_and_still_returns_the_results(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "value-secret-7c2e"
    jev = _Jev([{"tool": {}}, _quiet(looping=0.8)])
    agent = _agent(tmp_path, "shadow", jev)
    agent.memory.write("boot", secret)
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools([ToolCall("recall", {"key": "boot"})])
    assert results[0].output == secret
    assert "pack=supervisor" in caplog.text
    assert "side=loop" in caplog.text
    assert "reason=looping" in caplog.text
    assert "looping=true" in caplog.text
    assert "enforced=false" in caplog.text
    assert secret not in caplog.text


def test_completion_evidence_omits_the_reply(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    prompt = "caller-secret-7c2e"
    jev = _Jev([_wide(), _guards(), _tier(), _guards(), _quiet(done=0.9, progress=2.5)])
    model = _Model()
    agent = _agent(tmp_path, "shadow", jev, model)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete(prompt)
    assert result == {"text": "ready", "model": "hermes-model"}
    state = jev.calls[-1][0]
    assert state["steps"][0]["status"] == "ran"
    assert state["evidence"] == [{"id": "model", "text": "hermes-model"}, {"id": "skills", "text": "1"}]
    assert "ready" not in json.dumps(state)
    assert prompt not in json.dumps(state)
    assert "reason=complete" in caplog.text
    assert "done=true" in caplog.text
    assert prompt not in caplog.text


def test_soft_still_returns_the_model_text_when_the_steps_look_looping(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    jev = _Jev([_wide(), _guards(), _tier(), _guards(), _quiet(looping=0.9)])
    model = _Model()
    agent = _agent(tmp_path, "soft", jev, model)
    with caplog.at_level("INFO", logger="hermes.jev"):
        assert agent.complete("status") == {"text": "ready", "model": "hermes-model"}
    assert "reason=looping" in caplog.text
    assert "side=completion" in caplog.text
    assert "enforced=false" in caplog.text
    assert "effective=refuse" not in caplog.text


def _tool_ok(choice: str = "remember", calls: int = 2) -> dict[str, object]:
    answers: dict[str, object] = {
        "needs_tool": {"type": "noul", "noul": 0.8},
        "tool": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }
    for index in range(calls):
        answers[f"safe::{index}"] = {"type": "noul", "noul": 0.8}
        answers[f"blast::{index}"] = {"type": "score", "score": 0.4}
    return answers


def _memory_kept() -> dict[str, object]:
    return {
        "worth": {"type": "noul", "noul": 0.8},
        "kind": {
            "type": "choice",
            "choice": "fact",
            "probabilities": {"fact": 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }


def test_soft_stops_calls_after_a_looping_judgment(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "value-secret-7c2e"
    jev = _Jev([_tool_ok(), _memory_kept(), _quiet(looping=UNSURE)])
    agent = _agent(tmp_path, "soft", jev)
    calls = [
        ToolCall("remember", {"key": "boot", "value": "kept"}),
        ToolCall("remember", {"key": "next", "value": secret}),
    ]
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools(calls)
    assert results[0].output == "stored"
    assert results[1].status == "stopped"
    assert results[1].output == STOP_TEXT
    assert agent.recall("boot") == "kept"
    with pytest.raises(FileNotFoundError):
        agent.recall("next")
    assert "reason=looping" in caplog.text
    assert "enforced=true" in caplog.text
    assert "effective=refuse" in caplog.text
    assert secret not in caplog.text
    assert len([call for call in jev.calls if "looping" in call[1]]) == 1


def test_soft_runs_the_rest_when_the_loop_noul_is_below_unsure(tmp_path: Path) -> None:
    jev = _Jev([_tool_ok(choice="list_skills"), _quiet(looping=UNSURE - 0.01), _quiet()])
    agent = _agent(tmp_path, "soft", jev)
    results = agent.run_tools([ToolCall("list_skills", {}), ToolCall("list_skills", {})])
    assert [result.status for result in results] == ["ran", "ran"]


def test_soft_runs_the_rest_when_the_evidence_looks_complete(tmp_path: Path) -> None:
    jev = _Jev(
        [
            _tool_ok(choice="list_skills"),
            _quiet(done=UNSURE, progress=float(PROGRESS_LEVEL)),
            _quiet(),
        ]
    )
    agent = _agent(tmp_path, "soft", jev)
    results = agent.run_tools([ToolCall("list_skills", {}), ToolCall("list_skills", {})])
    assert [result.status for result in results] == ["ran", "ran"]


def test_soft_jev_error_still_runs_the_rest_of_the_batch(tmp_path: Path) -> None:
    jev = _Jev([_tool_ok(choice="list_skills"), JevError("Jev request failed", 429), _quiet()])
    agent = _agent(tmp_path, "soft", jev)
    results = agent.run_tools([ToolCall("list_skills", {}), ToolCall("list_skills", {})])
    assert [result.status for result in results] == ["ran", "ran"]
    assert [result.output for result in results] == ["alpha 1.0.0", "alpha 1.0.0"]


def test_shadow_still_runs_a_batch_that_looks_like_a_loop(tmp_path: Path) -> None:
    jev = _Jev([{"tool": {}}, _quiet(looping=UNSURE)])
    agent = _agent(tmp_path, "shadow", jev)
    results = agent.run_tools([ToolCall("list_skills", {}), ToolCall("list_skills", {})])
    assert [result.status for result in results] == ["ran", "ran"]
    assert len(jev.calls) == 2


def test_a_held_completion_is_supervised_without_the_reply(
    tmp_path: Path,
) -> None:
    prompt = "caller-secret-7c2e"
    jev = _Jev([_wide(), _block(), _quiet()])
    model = _Model()
    agent = _agent(tmp_path, "soft", jev, model)
    result = agent.complete(prompt)
    assert result["text"] == BLOCK_TEXT
    assert model.prompts == []
    state = jev.calls[-1][0]
    assert state["steps"][0]["status"] == "held"
    assert prompt not in json.dumps(state)
    assert "ready" not in json.dumps(state)


def test_jev_error_still_returns_the_tool_result(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    jev = _Jev([JevError("Jev request failed", 429), JevError("Jev request failed", 429)])
    agent = _agent(tmp_path, "shadow", jev)
    with caplog.at_level("INFO", logger="hermes.jev"):
        results = agent.run_tools([ToolCall("list_skills", {})])
    assert results[0].status == "ran"
    assert results[0].output == "alpha 1.0.0"
    assert "reason=jev_error" in caplog.text
    assert "side=loop" in caplog.text


def test_step_limit_does_not_call_the_supervisor(tmp_path: Path) -> None:
    jev = _Jev([_quiet()])
    agent = _agent(tmp_path, "shadow", jev)
    with pytest.raises(ValueError, match="limited"):
        agent.run_tools([ToolCall("list_skills", {})] * 5)
    assert jev.calls == []
