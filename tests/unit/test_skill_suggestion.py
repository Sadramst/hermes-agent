"""Skill suggestion in shadow. Recorded answers only. No live TypeSafe call."""

import json
import logging
from pathlib import Path

import pytest

from agent.decisions.skill_suggestion import (
    ADVISORY_NONE,
    EXCERPT_CHARS,
    FITS_QUESTION,
    GATE_QUESTIONS,
    RERANK,
    WHICH,
    Suggestion,
    record_suggestion,
    suggest,
    suggestion_block,
)
from agent.prompt import index_description
from services.jev import JevResult
from skills.loader import Skill


class _Jev:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        return JevResult(model="jev-1.13.0", answers=self.responses[len(self.calls) - 1], usage={})


def _skill(name: str, purpose: str, extra: str = "") -> Skill:
    body = f"# Purpose\n{purpose}\n"
    if extra:
        body += f"\n{extra}\n"
    return Skill(name=name, version="1.0.0", path=Path(name) / "SKILL.md", body=body)


def _which(choice: str, probabilities: dict[str, float]) -> dict[str, object]:
    return {
        "type": "choice",
        "choice": choice,
        "probabilities": probabilities,
        "confidence": 0.8,
    }


def _wide(choice: str, probabilities: dict[str, float], noul: float, prose: float) -> dict[str, object]:
    return {
        "which": _which(choice, probabilities),
        "gate::acts_on_user_system": {"type": "noul", "noul": noul},
        "gate::would_follow_documented_procedure": {"type": "noul", "noul": noul},
        "gate::prose_suffices": {"type": "noul", "noul": prose},
    }


def _rerank(choice: str, names: list[str], fits: float) -> dict[str, object]:
    probabilities = {name: 0.1 for name in names}
    probabilities[choice] = 0.6
    probabilities["none"] = 0.1
    answers: dict[str, object] = {"which": _which(choice, probabilities)}
    for name in names:
        answers[f"fits::{name}"] = {"type": "noul", "noul": fits}
    return answers


def test_suggestion_block_names_one_skill_or_says_nothing_fits() -> None:
    named = suggestion_block("beta")
    assert named == (
        "<skill_relevance>\n"
        "Relevant to the current request: beta. Ignore this if it does not fit "
        "what the user actually asked for.\n"
        "</skill_relevance>"
    )
    quiet = suggestion_block(None)
    assert ADVISORY_NONE in quiet
    assert "Relevant to the current request" not in quiet
    assert "UNTRUSTED-PROMPT-9f3a" not in named
    assert "UNTRUSTED-PROMPT-9f3a" not in quiet


def test_no_skills_makes_no_call() -> None:
    jev = _Jev([])
    result = suggest(jev, "status", [])
    assert result == Suggestion(name=None, reason="no_skills", answers={}, model="")
    assert jev.calls == []


def test_gate_below_the_cookbook_label_makes_one_call() -> None:
    skill = _skill("alpha", "Alpha skill")
    jev = _Jev([_wide("alpha", {"alpha": 0.8, "none": 0.2}, 0.1, 0.9)])
    result = suggest(jev, "status", [skill])
    assert len(jev.calls) == 1
    assert result.name is None
    assert result.reason == "gate"
    assert "rerank" not in result.answers


def test_gate_at_the_cookbook_label_reranks() -> None:
    skill = _skill("alpha", "Alpha skill")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.8, "none": 0.2}, 0.3, 0.7),
            _rerank("alpha", ["alpha"], 0.8),
        ]
    )
    result = suggest(jev, "status", [skill])
    assert len(jev.calls) == 2
    assert result.name == "alpha"
    assert result.reason == "ok"


def test_prose_suffices_counts_against_the_gate() -> None:
    skill = _skill("alpha", "Alpha skill")
    quiet = _Jev([_wide("alpha", {"alpha": 0.8, "none": 0.2}, 0.0, 1.0)])
    assert suggest(quiet, "explain", [skill]).reason == "gate"
    assert len(quiet.calls) == 1
    talk = _Jev(
        [
            _wide("alpha", {"alpha": 0.8, "none": 0.2}, 0.0, 0.0),
            _rerank("alpha", ["alpha"], 0.8),
        ]
    )
    assert suggest(talk, "explain", [skill]).name == "alpha"
    assert len(talk.calls) == 2


def test_one_skill_still_gets_a_rerank_call() -> None:
    skill = _skill("alpha", "Alpha skill", "EXCERPT_MARKER detailed procedure")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.2, "none": 0.8}, 0.9, 0.1),
            _rerank("alpha", ["alpha"], 0.30),
        ]
    )
    result = suggest(jev, "status", [skill])
    assert result.name == "alpha"
    assert result.reason == "ok"
    wide = jev.calls[0][1]
    assert wide["which"]["instructions"] == WHICH
    assert wide["which"]["criteria"]["alpha"] == index_description(skill.body)
    assert "EXCERPT_MARKER" not in wide["which"]["criteria"]["alpha"]
    assert wide["gate::prose_suffices"]["instructions"] == GATE_QUESTIONS["prose_suffices"]
    rerank = jev.calls[1][1]
    assert rerank["which"]["instructions"] == RERANK
    assert set(rerank["which"]["criteria"]) == {"none", "alpha"}
    assert "EXCERPT_MARKER" in rerank["which"]["criteria"]["alpha"]
    fits = rerank["fits::alpha"]["instructions"]
    assert fits["question"] == FITS_QUESTION
    assert fits["candidate"]["name"] == "alpha"
    assert len(fits["candidate"]["description"].split(" — ", 1)[1]) <= EXCERPT_CHARS


def test_ranking_ignores_none_and_unknown_names() -> None:
    skills = [_skill("alpha", "Alpha"), _skill("beta", "Beta"), _skill("gamma", "Gamma")]
    jev = _Jev(
        [
            _wide(
                "alpha",
                {"none": 0.70, "stranger": 0.20, "alpha": 0.05, "beta": 0.03, "gamma": 0.02},
                0.9,
                0.1,
            ),
            _rerank("beta", ["alpha", "beta", "gamma"], 0.8),
        ]
    )
    result = suggest(jev, "status", skills)
    assert result.name == "beta"
    assert set(jev.calls[1][1]["which"]["criteria"]) == {"none", "alpha", "beta", "gamma"}


def test_empty_shortlist_skips_the_second_call() -> None:
    skill = _skill("alpha", "Alpha")
    jev = _Jev([_wide("none", {"none": 0.7, "stranger": 0.3}, 0.9, 0.1)])
    result = suggest(jev, "status", [skill])
    assert len(jev.calls) == 1
    assert result.reason == "no_shortlist"
    assert result.name is None


def test_choice_none_suggests_nothing() -> None:
    skill = _skill("alpha", "Alpha")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.9, "none": 0.1}, 0.9, 0.1),
            _rerank("none", ["alpha"], 0.9),
        ]
    )
    result = suggest(jev, "status", [skill])
    assert result.name is None
    assert result.reason == "none"


def test_choice_outside_the_shortlist_suggests_nothing() -> None:
    skills = [
        _skill("alpha", "Alpha"),
        _skill("beta", "Beta"),
        _skill("gamma", "Gamma"),
        _skill("delta", "Delta"),
    ]
    wide = _wide(
        "delta",
        {"alpha": 0.4, "beta": 0.3, "gamma": 0.2, "delta": 0.05, "none": 0.05},
        0.9,
        0.1,
    )
    rerank = _rerank("delta", ["alpha", "beta", "gamma"], 0.9)
    jev = _Jev([wide, rerank])
    result = suggest(jev, "status", skills)
    assert result.name is None
    assert result.reason == "unknown"
    assert set(jev.calls[1][1]["which"]["criteria"]) == {"none", "alpha", "beta", "gamma"}


def test_fits_below_the_cookbook_label_drops_the_shortlist() -> None:
    skill = _skill("alpha", "Alpha")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.9, "none": 0.1}, 0.9, 0.1),
            _rerank("alpha", ["alpha"], 0.29),
        ]
    )
    result = suggest(jev, "status", [skill])
    assert result.name is None
    assert result.reason == "fits"


def test_user_prompt_stays_in_state_and_out_of_questions() -> None:
    request = "UNTRUSTED-PROMPT-9f3a"
    skill = _skill("alpha", "Alpha skill", "steps go here")
    jev = _Jev(
        [
            _wide("alpha", {"alpha": 0.9, "none": 0.1}, 0.9, 0.1),
            _rerank("alpha", ["alpha"], 0.8),
        ]
    )
    suggest(jev, request, [skill])
    for state, questions in jev.calls:
        assert state["request"] == request
        assert request not in json.dumps(questions)


def test_too_many_skills_raise_before_a_call() -> None:
    skills = [_skill(f"s{index}", "Purpose") for index in range(255)]
    jev = _Jev([])
    with pytest.raises(ValueError, match="255"):
        suggest(jev, "status", skills)
    assert jev.calls == []


def test_a_skill_named_none_is_rejected() -> None:
    jev = _Jev([])
    with pytest.raises(ValueError, match="none"):
        suggest(jev, "status", [_skill("none", "Nope")])
    assert jev.calls == []


def test_malformed_answer_raises() -> None:
    jev = _Jev([{"which": {}}])
    with pytest.raises(ValueError, match="incomplete"):
        suggest(jev, "status", [_skill("alpha", "Alpha")])


def test_record_keeps_the_comparison_and_omits_the_request(caplog: pytest.LogCaptureFixture) -> None:
    request = "secret-caller-prompt"
    with caplog.at_level(logging.INFO, logger="hermes.jev"):
        record = record_suggestion(
            mode="shadow",
            model="jev-1.13.0",
            skill_names=["alpha", "beta"],
            answers={"wide": {"which": {"choice": "alpha"}}},
            suggested="alpha",
            reason="ok",
        )
    comparison = record["comparison"]
    assert comparison["suggested"] == "alpha"
    assert comparison["reason"] == "ok"
    assert comparison["hermes_index"] == ["alpha", "beta"]
    assert comparison["suggestion_in_prompt"] is False
    assert record["proposed"] == "advise"
    assert record["effective"] == "advise"
    assert request not in caplog.text
    assert "suggested=alpha" in caplog.text
    assert "hermes_index=alpha,beta" in caplog.text
    assert "suggestion_in_prompt=false" in caplog.text
    quiet = record_suggestion(
        mode="shadow",
        model="jev-1.13.0",
        skill_names=["alpha"],
        answers={},
        suggested="",
        reason="gate",
    )
    assert quiet["proposed"] == "fallback_llm"
    assert quiet["effective"] == "advise"
    assert quiet["comparison"]["suggestion_in_prompt"] is False
