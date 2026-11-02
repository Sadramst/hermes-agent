from __future__ import annotations

import pytest

from agent.decisions.gateway_skill_line import suggest_skill_result
from agent.decisions.skill_suggestion import suggestion_block
from services.jev import JevError, JevResult


class _Jev:
    def __init__(self, answers: dict[str, object] | None = None, *, error: bool = False) -> None:
        self.answers = answers or {}
        self.error = error
        self.calls = 0

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls += 1
        if self.error:
            raise JevError("down")
        return JevResult(model="jev-1.13.0", answers=self.answers, usage={})


ROSTER = [
    {"name": "deploy", "description": "Promote the Hermes agent to production."},
    {"name": "ping", "description": "Reply with a short health word."},
]


def test_mode_off_is_unavailable_without_jev_call() -> None:
    client = _Jev()
    out = suggest_skill_result(
        mode="off",
        client=client,
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out == {
        "available": False,
        "line": "",
        "suggested": "",
        "reason": "unavailable",
        "model": "",
    }
    assert client.calls == 0


def test_empty_skills_raises_before_jev() -> None:
    client = _Jev()
    with pytest.raises(ValueError, match="skills"):
        suggest_skill_result(
            mode="shadow",
            client=client,
            settings_model="jev-1.13.0",
            request="hello",
            skills=[],
        )
    assert client.calls == 0


def test_shadow_returns_line_when_pack_picks_a_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.decisions import gateway_skill_line as mod

    class S:
        name = "deploy"
        reason = "ok"
        answers: dict[str, object] = {}
        model = "jev-1.13.0"

    monkeypatch.setattr(mod, "suggest", lambda client, request, skills: S())
    out = suggest_skill_result(
        mode="shadow",
        client=_Jev(),
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out["available"] is True
    assert out["suggested"] == "deploy"
    assert out["line"] == suggestion_block("deploy")
    assert out["reason"] == "ok"
    assert out["model"] == "jev-1.13.0"


def test_jev_error_returns_empty_line(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.decisions import gateway_skill_line as mod

    def boom(client: object, request: str, skills: list[object]) -> object:
        raise JevError("down")

    monkeypatch.setattr(mod, "suggest", boom)
    out = suggest_skill_result(
        mode="soft",
        client=_Jev(),
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out["available"] is True
    assert out["line"] == ""
    assert out["suggested"] == ""
    assert out["reason"] == "jev_error"
