"""Tool-call pack v1.

Shadow logs which tool Jev would pick and still runs the allowlist.
Soft holds a call unless Jev picked it, the need is not a clear no, the safety
noul is above unsure, and the blast score is below the irreversible level.
Cookbook probability cutoffs are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import (
    ChoiceQuestion,
    NoulQuestion,
    ScoreQuestion,
    render_choice,
    render_noul,
    render_score,
)
from agent.decisions.state import tool_state
from agent.tools import TOOL_ARGUMENTS, ToolCall

PACK = "tool-call"
PACK_VERSION = "1"
EXCERPT_CHARS = 2000

NEEDS = "Do the proposed calls need a tool?"
NEEDS_YES = "The work cannot be finished without running one of these calls."
NEEDS_NO = "The work does not need a tool."

WHICH = "Which tool, if any, fits the proposed calls?"
NONE_CRITERIA = "No tool should run."
TOOL_CRITERIA = {
    "recall": "Read one stored memory record.",
    "remember": "Store one memory record.",
    "list_skills": "List the loaded skills.",
    "read_skill": "Read the full instructions of one loaded skill.",
    "search_documents": "Search saved knowledge base documents.",
    "save_document": "Save one document into the knowledge base.",
    "search_memory": "Search stored memory records by meaning or keyword.",
    "delete_memory": "Delete one memory record.",
    "delegate_to_grok": "Send one task to Grok. The payload is the task text.",
}

SAFE = "Can the call identified by `call_id` run without a person?"
SAFE_YES = "A person does not need to approve this call before it runs."
SAFE_NO = "A person should approve this call before it runs."

BLAST = "How much harm could result if the call identified by `call_id` ran?"
BLAST_LEVELS = (
    "Running it only reads information the caller already asked to see",
    "Running it stores a note the caller asked to keep",
    "Running it changes a record the caller can replace",
    "Running it deletes a record or takes an irreversible action",
)

# A needs noul below this means a tool was not called for. Exactly this value can continue.
NEEDS_LABEL = 0.5

# A safe noul at or below this asks a person. Near 0.5 means the judge is unsure.
# Auto-run requires a noul above this line. It is not a vendor 0.90 cutoff.
UNSURE = 0.5

# Index of the level whose text is deletion or another irreversible action.
# A score at or above this asks a person. It is not a vendor probability.
HARM_LEVEL = 3


@dataclass(frozen=True)
class ToolJudgment:
    choice: str
    reason: str
    answers: dict[str, Any]
    model: str


def judge(client: object, calls: list[ToolCall]) -> ToolJudgment:
    """Ask once about one batch. The caller still decides which calls run."""
    if not calls:
        raise ValueError("Tool batch is empty")
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    rows = [_row(index, call) for index, call in enumerate(calls)]
    result = evaluate(tool_state(rows), _questions(rows))
    answers = _answers(result)
    choice, reason = label_tools(answers, [row["id"] for row in rows])
    model = getattr(result, "model", "")
    return ToolJudgment(
        choice=choice,
        reason=reason,
        answers=answers,
        model=model if isinstance(model, str) else "",
    )


def label_tools(answers: dict[str, Any], call_ids: list[str]) -> tuple[str, str]:
    """Return Jev's tool choice, or an empty choice with the reason it was dropped."""
    _noul(answers.get("needs_tool"))
    which = answers.get("tool")
    if not isinstance(which, dict) or not isinstance(which.get("choice"), str):
        raise ValueError("Choice answer is incomplete")
    for call_id in call_ids:
        _noul(answers.get(f"safe::{call_id}"))
        _score(answers.get(f"blast::{call_id}"))
    choice = which["choice"]
    if choice == "none":
        return "", "none"
    if choice not in TOOL_ARGUMENTS:
        return "", "unknown"
    if _noul(answers.get("needs_tool")) < NEEDS_LABEL:
        return choice, "needs"
    return choice, "ok"


def hold_for(*, name: str, index: int, choice: str, reason: str, answers: dict[str, Any]) -> str:
    """Return run, ask_person, or refused for a call the allowlist would otherwise run."""
    if reason == "jev_error":
        return "ask_person"
    if reason != "ok" or name != choice:
        return "refused"
    if _score(answers.get(f"blast::{index}")) >= HARM_LEVEL:
        return "ask_person"
    if _noul(answers.get(f"safe::{index}")) <= UNSURE:
        return "ask_person"
    return "run"


def logged_names(calls: list[ToolCall]) -> list[str]:
    """Allowlisted names only. Anything else is recorded as unknown."""
    return [call.name if call.name in TOOL_ARGUMENTS else "unknown" for call in calls]


def record_tools(
    *,
    mode: str,
    model: str,
    call_names: list[str],
    choice: str,
    statuses: list[str],
    answers: dict[str, Any],
    reason: str,
    enforced: bool = False,
) -> dict[str, object]:
    """Log the judgment. The record omits argument values."""
    if reason == "ok":
        proposed = "advise"
    elif reason == "jev_error":
        proposed = "ask_person"
    else:
        proposed = "refuse"
    if enforced and reason == "ok":
        if "ask_person" in statuses:
            proposed = "ask_person"
        elif "ran" not in statuses:
            proposed = "refuse"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["calls"],
        answers=answers,
        proposed=proposed,
        effective=proposed if enforced else "advise",
        comparison={
            "call_names": list(call_names),
            "tool": choice,
            "statuses": list(statuses),
            "reason": reason,
            "enforced": enforced,
        },
    )


def _row(index: int, call: ToolCall) -> dict[str, object]:
    arguments = {
        key: " ".join(value.split())[:EXCERPT_CHARS]
        for key, value in call.arguments.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    return {"id": str(index), "name": call.name, "arguments": arguments}


def _questions(rows: list[dict[str, object]]) -> dict[str, object]:
    criteria = {"none": NONE_CRITERIA, **TOOL_CRITERIA}
    questions: dict[str, object] = {
        "needs_tool": render_noul(NoulQuestion(NEEDS, {"true": NEEDS_YES, "false": NEEDS_NO})),
        "tool": render_choice(ChoiceQuestion(WHICH, criteria)),
    }
    for row in rows:
        pointer = {"call_id": row["id"]}
        questions[f"safe::{row['id']}"] = render_noul(
            NoulQuestion({"question": SAFE, **pointer}, {"true": SAFE_YES, "false": SAFE_NO})
        )
        questions[f"blast::{row['id']}"] = render_score(
            ScoreQuestion({"question": BLAST, **pointer}, BLAST_LEVELS)
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
