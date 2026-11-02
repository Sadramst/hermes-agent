"""Chroma passage judgments stay in state and out of the search response."""

import json

import pytest

from agent.decisions.passage_filter import (
    EXCERPT_CHARS,
    HELPS,
    RELEVANCE,
    RELEVANCE_LEVELS,
    SHOW_LEVEL,
    judge,
    record_passages,
    shown_ids,
    visible_matches,
)
from services.jev import JevResult


class _Jev:
    def __init__(self, answers: dict[str, object]) -> None:
        self.answers = answers
        self.calls: list[tuple[object, dict[str, object]]] = []

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls.append((state, questions))
        return JevResult(model="jev-1.13.0", answers=self.answers, usage={})


def _answers() -> dict[str, object]:
    return {
        "helps::note-1": {"type": "noul", "noul": 0.8},
        "relevance::note-1": {"type": "score", "score": 2.4},
        "helps::note-2": {"type": "noul", "noul": 0.1},
        "relevance::note-2": {"type": "score", "score": 0.2},
    }


def test_one_request_names_each_passage_without_copying_its_text() -> None:
    query = "query-secret-7c2e"
    passage = "passage-secret-9af1 " + ("word " * 800)
    jev = _Jev(_answers())
    result = judge(
        jev,
        query,
        [
            {"id": "note-1", "text": passage, "distance": 0.2},
            {"id": "note-1", "text": "duplicate", "distance": 0.3},
            {"id": "note-2", "text": "other", "distance": 0.4},
        ],
    )
    assert result.reason == "ok"
    assert len(jev.calls) == 1
    state, questions = jev.calls[0]
    assert state["query"] == query
    assert state["passages"][0]["text"] == " ".join(passage.split())[:EXCERPT_CHARS]
    assert len(state["passages"][0]["text"]) == EXCERPT_CHARS
    dumped = json.dumps(questions)
    assert query not in dumped
    assert "passage-secret-9af1" not in dumped
    assert questions["helps::note-1"]["instructions"]["question"] == HELPS
    assert questions["helps::note-1"]["instructions"]["passage_id"] == "note-1"
    assert questions["relevance::note-2"]["instructions"]["question"] == RELEVANCE
    assert questions["relevance::note-2"]["criteria"] == list(RELEVANCE_LEVELS)


def test_empty_matches_make_no_jev_call() -> None:
    jev = _Jev({})
    result = judge(jev, "tuesday", [])
    assert result.reason == "no_matches"
    assert jev.calls == []


def test_a_missing_score_is_rejected() -> None:
    jev = _Jev({"helps::note-1": {"type": "noul", "noul": 0.5}})
    with pytest.raises(ValueError, match="incomplete"):
        judge(jev, "tuesday", [{"id": "note-1", "text": "meeting"}])


def test_shown_ids_keep_a_score_on_the_helping_level() -> None:
    answers = _answers()
    answers["relevance::note-2"] = {"type": "score", "score": SHOW_LEVEL}
    assert shown_ids(answers, ["note-1", "note-2"]) == ["note-1", "note-2"]
    answers["relevance::note-2"] = {"type": "score", "score": SHOW_LEVEL - 0.01}
    assert shown_ids(answers, ["note-1", "note-2"]) == ["note-1"]


def test_visible_matches_keep_neighbor_order_and_unjudged_rows() -> None:
    matches = [
        {"id": "note-2", "text": "second"},
        {"id": "", "text": "blank"},
        {"id": "note-1", "text": "first"},
    ]
    assert visible_matches(matches, ["note-1"]) == [
        {"id": "", "text": "blank"},
        {"id": "note-1", "text": "first"},
    ]


def test_record_keeps_ids_and_does_not_mark_the_response_filtered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="hermes.jev"):
        record = record_passages(
            mode="shadow",
            model="jev-1.13.0",
            match_ids=["note-1", "note-2"],
            shown=["note-1"],
            answers=_answers(),
            reason="ok",
            filtered=False,
        )
    assert record["comparison"]["filtered"] is False
    assert record["comparison"]["match_ids"] == ["note-1", "note-2"]
    assert record["comparison"]["shown"] == ["note-1"]
    assert "pack=chroma-passage" in caplog.text
    assert "matches=note-1,note-2" in caplog.text
    assert "shown=note-1" in caplog.text
    assert "filtered=false" in caplog.text
    assert "reason=ok" in caplog.text
    assert "query-secret" not in caplog.text
