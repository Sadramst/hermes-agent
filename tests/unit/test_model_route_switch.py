"""Soft mode may pass HERMES_MODEL_SMALL into the completion client."""

from pathlib import Path

import pytest

from agent.core import HermesAgent
from agent.decisions.model_router import RouteJudgment
from services.chroma import ChromaClient
from services.jev import JevError
from utils.settings import load_settings


class _Model:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.models: list[str | None] = []
        self.model = "frontier-model"

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        self.models.append(model)
        return "ok"


def _agent(tmp_path: Path, mode: str, model: _Model, *, model_small: str | None = None) -> HermesAgent:
    values = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
        "HERMES_MEMORY_DIR": str(tmp_path / "memory"),
        "HERMES_SKILLS_DIR": str(tmp_path / "skills"),
        "HERMES_MODEL_BASE_URL": "https://models.example/v1",
        "HERMES_MODEL_NAME": "frontier-model",
        "HERMES_MODEL_API_KEY": "0123456789abcdef",
        "HERMES_JEV_MODE": mode,
        "HERMES_JEV_API_KEY": "fedcba9876543210",
    }
    if model_small is not None:
        values["HERMES_MODEL_SMALL"] = model_small
    return HermesAgent(
        load_settings(values),
        chroma_client=ChromaClient("chromadb", 8000, opener=lambda request, timeout: None),
        model_client=model,
        jev_client=object(),
    )


def _patch_jev_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agent.core._guard_screen", lambda **kwargs: "pass")
    monkeypatch.setattr("agent.core._skill_suggestion", lambda **kwargs: None)
    monkeypatch.setattr("agent.core._supervise", lambda **kwargs: False)


def test_soft_small_ok_uses_hermes_model_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_jev_helpers(monkeypatch)
    monkeypatch.setattr(
        "agent.core.judge_route",
        lambda client, request: RouteJudgment(
            tier="small", reason="ok", answers={}, model="jev"
        ),
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", model, model_small="cheap")
    result = agent.complete("easy turn")
    assert result == {"text": "ok", "model": "frontier-model"}
    assert model.models[-1] == "cheap"


def test_soft_without_small_stays_on_frontier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_jev_helpers(monkeypatch)
    monkeypatch.setattr(
        "agent.core.judge_route",
        lambda client, request: RouteJudgment(
            tier="small", reason="ok", answers={}, model="jev"
        ),
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", model)
    agent.complete("easy turn")
    assert model.models[-1] == "frontier-model"


def test_shadow_never_switches_even_with_small_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_jev_helpers(monkeypatch)
    monkeypatch.setattr(
        "agent.core.judge_route",
        lambda client, request: RouteJudgment(
            tier="small", reason="ok", answers={}, model="jev"
        ),
    )
    model = _Model()
    agent = _agent(tmp_path, "shadow", model, model_small="cheap")
    agent.complete("easy turn")
    assert model.models[-1] == "frontier-model"


def test_soft_reason_up_stays_on_frontier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_jev_helpers(monkeypatch)
    monkeypatch.setattr(
        "agent.core.judge_route",
        lambda client, request: RouteJudgment(
            tier="frontier", reason="up", answers={}, model="jev"
        ),
    )
    model = _Model()
    agent = _agent(tmp_path, "soft", model, model_small="cheap")
    agent.complete("easy turn")
    assert model.models[-1] == "frontier-model"


def test_soft_jev_error_stays_on_frontier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_jev_helpers(monkeypatch)

    def _raise_jev(client: object, request: str) -> RouteJudgment:
        raise JevError("Jev request failed", 429)

    monkeypatch.setattr("agent.core.judge_route", _raise_jev)
    model = _Model()
    agent = _agent(tmp_path, "soft", model, model_small="cheap")
    agent.complete("easy turn")
    assert model.models[-1] == "frontier-model"
