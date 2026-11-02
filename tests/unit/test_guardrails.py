"""Guardrail labels stay in the log and out of the completion."""

import json

import pytest

from agent.decisions.guardrails import (
    BLAST,
    BLAST_LEVELS,
    IRREVERSIBLE_LEVEL,
    UNSURE,
    label_route,
    record_screen,
    screen,
)
from services.jev import JevResult


class _Jev:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        return JevResult(model="jev-1.13.0", answers=self.answers, usage={})


def _clear() -> dict[str, object]:
    return {
        "jailbreak": {"type": "noul", "noul": 0.01},
        "credential_harvest": {"type": "noul", "noul": 0.01},
        "self_harm": {"type": "noul", "noul": 0.01},
        "blast_radius": {"type": "score", "score": 0.2},
    }


def test_a_clear_message_passes_and_stays_out_of_the_questions() -> None:
    text = "caller-secret-7c2e"
    jev = _Jev(_clear())
    result = screen(jev, "inbound", text)
    assert result.route == "pass"
    state, questions = jev.calls[0]
    assert state == {"text": text}
    dumped = json.dumps(questions)
    assert text not in dumped
    assert questions["jailbreak"]["criteria"]["true"]
    assert questions["blast_radius"]["instructions"] == BLAST
    assert questions["blast_radius"]["criteria"] == list(BLAST_LEVELS)


def test_an_unsure_hazard_is_review_and_an_irreversible_score_is_block() -> None:
    answers = _clear()
    answers["jailbreak"] = {"type": "noul", "noul": UNSURE}
    assert label_route(answers) == "review"
    answers["blast_radius"] = {"type": "score", "score": IRREVERSIBLE_LEVEL}
    assert label_route(answers) == "block"
    answers["blast_radius"] = {"type": "score", "score": IRREVERSIBLE_LEVEL - 0.01}
    answers["self_harm"] = {"type": "noul", "noul": 0.99}
    assert label_route(answers) == "review"


def test_outbound_questions_ask_about_the_reply() -> None:
    jev = _Jev(_clear())
    screen(jev, "outbound", "reply-secret-4ab1")
    question = jev.calls[0][1]["credential_harvest"]["instructions"]
    assert "reply" in question
    assert "reply-secret-4ab1" not in json.dumps(jev.calls[0][1])


def test_record_logs_review_without_enforcing_it(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="hermes.jev"):
        record = record_screen(
            mode="shadow",
            model="jev-1.13.0",
            side="inbound",
            route="review",
            answers={},
            reason="jev_error",
        )
    assert record["proposed"] == "ask_person"
    assert record["effective"] == "advise"
    assert record["comparison"]["enforced"] is False
    assert "pack=guardrails" in caplog.text
    assert "route=review" in caplog.text
    assert "side=inbound" in caplog.text
    assert "reason=jev_error" in caplog.text
    assert "enforced=false" in caplog.text


def test_enforced_review_asks_a_person() -> None:
    record = record_screen(
        mode="soft",
        model="jev-1.13.0",
        side="inbound",
        route="block",
        answers={},
        reason="ok",
        enforced=True,
    )
    assert record["proposed"] == "refuse"
    assert record["effective"] == "refuse"
    assert record["comparison"]["enforced"] is True


def test_a_missing_noul_is_rejected() -> None:
    jev = _Jev({"blast_radius": {"type": "score", "score": 0.0}})
    with pytest.raises(ValueError, match="incomplete"):
        screen(jev, "inbound", "status")
