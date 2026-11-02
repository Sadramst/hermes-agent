"""Chroma passage filter pack v1.

Shadow logs one Noul and one Score per match and returns every neighbor.
Soft returns only passages whose relevance score reaches the helping level.
A Jev error returns every neighbor. Cookbook probabilities are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import NoulQuestion, ScoreQuestion, render_noul, render_score
from agent.decisions.policy import effective_outcome
from agent.decisions.state import search_state

PACK = "chroma-passage"
PACK_VERSION = "1"
EXCERPT_CHARS = 2000

HELPS = "Does the passage identified by `passage_id` help answer the query?"
RELEVANCE = "How relevant is the passage identified by `passage_id` to the query?"
RELEVANCE_LEVELS = (
    "The passage is about a different subject from the query",
    "The passage shares the query's subject and does not state an answer",
    "The passage states information that helps answer the query",
    "The passage states the specific fact or procedure the query asks for",
)
# Index of the first level that says the passage states an answer. Not a cookbook cutoff.
SHOW_LEVEL = 2


@dataclass(frozen=True)
class PassageJudgment:
    reason: str
    answers: dict[str, Any]
    model: str


def judge(client: object, query: str, matches: list[dict[str, object]]) -> PassageJudgment:
    """Ask one request about the matches. An empty list makes no Jev call."""
    rows = passage_rows(matches)
    if not rows:
        return PassageJudgment(reason="no_matches", answers={}, model="")
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    result = evaluate(search_state(query, rows), _questions(rows))
    answers = _answers(result)
    for row in rows:
        _noul(answers.get(f"helps::{row['id']}"))
        _score(answers.get(f"relevance::{row['id']}"))
    model = getattr(result, "model", "")
    return PassageJudgment(
        reason="ok",
        answers=answers,
        model=model if isinstance(model, str) else "",
    )


def passage_rows(matches: list[dict[str, object]]) -> list[dict[str, str]]:
    """One row per document id. Passage text is an excerpt for the judge only."""
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for match in matches:
        doc_id = match.get("id")
        if not isinstance(doc_id, str) or not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        text = match.get("text")
        body = text if isinstance(text, str) else ""
        rows.append({"id": doc_id, "text": " ".join(body.split())[:EXCERPT_CHARS]})
    return rows


def shown_ids(answers: dict[str, Any], match_ids: list[str]) -> list[str]:
    """Ids whose relevance score reaches the helping level. Order follows the neighbors."""
    shown: list[str] = []
    for doc_id in match_ids:
        if _score(answers.get(f"relevance::{doc_id}")) >= SHOW_LEVEL:
            shown.append(doc_id)
    return shown


def visible_matches(
    matches: list[dict[str, object]],
    shown: list[str],
) -> list[dict[str, object]]:
    """Keep neighbor order. A row with no document id stays, because it was not judged."""
    keep = set(shown)
    visible: list[dict[str, object]] = []
    for match in matches:
        doc_id = match.get("id")
        if isinstance(doc_id, str) and doc_id and doc_id not in keep:
            continue
        visible.append(match)
    return visible


def record_passages(
    *,
    mode: str,
    model: str,
    match_ids: list[str],
    shown: list[str],
    answers: dict[str, Any],
    reason: str,
    filtered: bool,
) -> dict[str, object]:
    """Log the judgment. The record keeps document ids and omits query and passage text."""
    proposed = "advise" if reason == "ok" else "fallback_llm"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["query", "passages"],
        answers=answers,
        proposed=proposed,
        effective=effective_outcome(mode, proposed),
        comparison={
            "match_ids": list(match_ids),
            "shown": list(shown),
            "reason": reason,
            "filtered": filtered,
        },
    )


def _questions(rows: list[dict[str, str]]) -> dict[str, object]:
    questions: dict[str, object] = {}
    for row in rows:
        pointer = {"passage_id": row["id"]}
        questions[f"helps::{row['id']}"] = render_noul(
            NoulQuestion({"question": HELPS, **pointer})
        )
        questions[f"relevance::{row['id']}"] = render_score(
            ScoreQuestion({"question": RELEVANCE, **pointer}, RELEVANCE_LEVELS)
        )
    return questions


def _noul(answer: object) -> float:
    if not isinstance(answer, dict):
        raise ValueError("Noul answer is incomplete")
    value = answer.get("noul")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Noul answer is incomplete")
    return float(value)


def _score(answer: object) -> float:
    if not isinstance(answer, dict):
        raise ValueError("Score answer is incomplete")
    value = answer.get("score")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Score answer is incomplete")
    return float(value)


def _answers(result: object) -> dict[str, Any]:
    answers = getattr(result, "answers", None)
    if not isinstance(answers, dict):
        raise ValueError("Jev answer is incomplete")
    return answers
