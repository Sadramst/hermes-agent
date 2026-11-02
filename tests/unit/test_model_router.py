"""The model router logs a tier and leaves the completion on the frontier model."""

import json
from pathlib import Path

import pytest

from agent.core import HermesAgent
from agent.decisions.model_router import CONFIDENCE_UP, TIER, TIER_CRITERIA, judge, label_tier
from services.chroma import ChromaClient
from services.jev import JevError, JevResult
from utils.settings import load_settings

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "test_data" / "router" / "tasks.json"


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
        item = self.responses[len(scripted) - 1]
        if isinstance(item, Exception):
            raise item
        return JevResult(model="jev-1.13.0", answers=item, usage={})


def _tier(choice: str, confidence: float) -> dict[str, object]:
    return {
        "tier": {
            "type": "choice",
            "choice": choice,
            "probabilities": {choice: 0.8, "none": 0.2},
            "confidence": confidence,
        }
    }


def _guards() -> dict[str, object]:
    return {
        "jailbreak": {"type": "noul", "noul": 0.01},
        "credential_harvest": {"type": "noul", "noul": 0.01},
        "self_harm": {"type": "noul", "noul": 0.01},
        "blast_radius": {"type": "score", "score": 0.1},
    }


def _agent(tmp_path: Path, mode: str, jev: object, model: _Model) -> HermesAgent:
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


def test_frozen_tasks_name_frontier_and_small() -> None:
    payload = json.loads(TASKS.read_text(encoding="utf-8"))
    tiers = {task["tier"] for task in payload["tasks"]}
    assert tiers == {"frontier", "small"}
    assert {task["id"] for task in payload["tasks"]} == {"plan", "easy"}


def test_low_confidence_moves_up_to_frontier() -> None:
    small = _tier("small", CONFIDENCE_UP)
    assert label_tier(small) == ("frontier", "up")
    clear = _tier("small", CONFIDENCE_UP + 0.01)
    assert label_tier(clear) == ("small", "ok")
    assert label_tier(_tier("none", 0.9)) == ("frontier", "none")
    assert label_tier(_tier("frontier", 0.2)) == ("frontier", "ok")


def test_questions_omit_the_prompt() -> None:
    prompt = "caller-secret-7c2e"
    jev = _Jev([_tier("small", 0.9)])
    result = judge(jev, prompt)
    assert result.tier == "small"
    state, questions = jev.calls[0]
    assert state["request"] == prompt
    dumped = json.dumps(questions)
    assert prompt not in dumped
    assert questions["tier"]["instructions"] == TIER
    assert questions["tier"]["criteria"]["none"]
    assert set(questions["tier"]["criteria"]) == {"none", *TIER_CRITERIA}


def test_shadow_logs_a_small_tier_and_keeps_the_frontier_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    prompt = "caller-secret-7c2e"
    jev = _Jev([_guards(), _tier("small", 0.9), _guards()])
    model = _Model()
    agent = _agent(tmp_path, "shadow", jev, model)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete(prompt)
    assert result == {"text": "ready", "model": "hermes-model"}
    assert model.prompts[0].endswith(prompt)
    assert len(jev.calls) == 4
    assert jev.calls[1][0]["request"] == prompt
    assert prompt not in json.dumps(jev.calls[1][1])
    assert "pack=model-router" in caplog.text
    assert "tier=small" in caplog.text
    assert "enforced=false" in caplog.text
    assert prompt not in caplog.text


def test_soft_low_confidence_stays_on_the_frontier_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    jev = _Jev([_guards(), _tier("small", CONFIDENCE_UP), _guards()])
    model = _Model()
    agent = _agent(tmp_path, "soft", jev, model)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete("status")
    assert result["model"] == "hermes-model"
    assert "tier=frontier" in caplog.text
    assert "reason=up" in caplog.text
    assert len(model.prompts) == 1


def test_router_error_still_returns_the_frontier_model(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    jev = _Jev([_guards(), JevError("Jev request failed", 429), _guards()])
    model = _Model()
    agent = _agent(tmp_path, "shadow", jev, model)
    with caplog.at_level("INFO", logger="hermes.jev"):
        result = agent.complete("status")
    assert result == {"text": "ready", "model": "hermes-model"}
    assert "reason=jev_error" in caplog.text
    assert "tier=frontier" in caplog.text
