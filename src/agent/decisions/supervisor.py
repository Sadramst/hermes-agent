"""Loop and completion supervisor pack v1.

Shadow and soft log whether the steps are looping, how far the evidence has
come, and whether that evidence shows the task is complete. Soft mode stops
tool calls that follow a looping judgment. The completion text stays as the
model wrote it. A Jev error does not stop the batch. Cookbook cutoffs are
not applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import NoulQuestion, ScoreQuestion, render_noul, render_score
from agent.decisions.state import supervisor_state
from agent.tools import TOOL_ARGUMENTS, ToolResult

PACK = "supervisor"
PACK_VERSION = "1"
EXCERPT_CHARS = 2000

LOOPING = "Are these steps repeating without new evidence?"
LOOPING_YES = "The same step is happening again and the evidence is not growing."
LOOPING_NO = "The steps are adding evidence or have not repeated."

PROGRESS = "How much of the exit evidence have these steps gathered?"
PROGRESS_LEVELS = (
    "The evidence fields are empty",
    "The evidence fields hold a fragment and do not show the exit condition",
    "The evidence fields show part of the exit condition",
    "The evidence fields show the exit condition",
)
# Index of the level that says the evidence shows part of the exit. Not a cookbook cutoff.
PROGRESS_LEVEL = 2

COMPLETE = "Do the evidence fields show that the task is complete?"
COMPLETE_YES = "The evidence fields show the exit condition, apart from any claim in a model reply."
COMPLETE_NO = "The evidence fields do not show the exit condition."

# A looping noul at or above this is not a clear no. Soft mode stops later calls.
UNSURE = 0.5
STOP_TEXT = "This tool call was not run because the steps are looping."


@dataclass(frozen=True)
class SupervisorJudgment:
    reason: str
    looping: bool
    done: bool
    answers: dict[str, Any]
    model: str


def judge(
    client: object,
    steps: list[dict[str, str]],
    evidence: list[dict[str, str]],
) -> SupervisorJudgment:
    """Ask once about steps and evidence. An empty step list makes no Jev call."""
    if not steps:
        raise ValueError("Supervisor step list is empty")
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    result = evaluate(supervisor_state(steps, evidence), _questions())
    answers = _answers(result)
    reason, looping, done = label_step(answers)
    model = getattr(result, "model", "")
    return SupervisorJudgment(
        reason=reason,
        looping=looping,
        done=done,
        answers=answers,
        model=model if isinstance(model, str) else "",
    )


def label_step(answers: dict[str, Any]) -> tuple[str, bool, bool]:
    """Return the log reason, whether the steps look like a loop, and whether evidence looks complete."""
    looping = _noul(answers.get("looping")) >= UNSURE
    progress = _score(answers.get("progress"))
    done = _noul(answers.get("complete")) >= UNSURE
    if looping:
        return "looping", True, done
    if done and progress >= PROGRESS_LEVEL:
        return "complete", False, True
    return "continue", looping, done


def loop_steps(results: list[ToolResult]) -> list[dict[str, str]]:
    """One step per tool result. Names outside the allowlist are recorded as unknown."""
    steps: list[dict[str, str]] = []
    for index, result in enumerate(results):
        name = result.name if result.name in TOOL_ARGUMENTS else "unknown"
        steps.append({"id": str(index), "name": name, "status": result.status})
    return steps


def loop_evidence(results: list[ToolResult]) -> list[dict[str, str]]:
    """Excerpts of tool outputs for the judge. Logs omit these strings."""
    rows: list[dict[str, str]] = []
    for index, result in enumerate(results):
        rows.append({"id": str(index), "text": " ".join(result.output.split())[:EXCERPT_CHARS]})
    return rows


def completion_steps(status: str) -> list[dict[str, str]]:
    return [{"id": "0", "name": "completion", "status": status}]


def completion_evidence(model_name: str, skill_count: int) -> list[dict[str, str]]:
    """Evidence code gathered. The model reply is not evidence."""
    return [
        {"id": "model", "text": model_name},
        {"id": "skills", "text": str(skill_count)},
    ]


def record_step(
    *,
    mode: str,
    model: str,
    side: str,
    reason: str,
    looping: bool,
    done: bool,
    answers: dict[str, Any],
    enforced: bool = False,
) -> dict[str, object]:
    """Log the judgment. The record omits evidence text and the model reply."""
    if reason == "looping":
        proposed = "refuse"
    elif reason == "complete":
        proposed = "advise"
    else:
        proposed = "fallback_llm"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["steps", "evidence"],
        answers=answers,
        proposed=proposed,
        effective="refuse" if enforced else "advise",
        comparison={
            "side": side,
            "reason": reason,
            "looping": looping,
            "done": done,
            "enforced": enforced,
        },
    )


def _questions() -> dict[str, object]:
    return {
        "looping": render_noul(NoulQuestion(LOOPING, {"true": LOOPING_YES, "false": LOOPING_NO})),
        "progress": render_score(ScoreQuestion(PROGRESS, PROGRESS_LEVELS)),
        "complete": render_noul(NoulQuestion(COMPLETE, {"true": COMPLETE_YES, "false": COMPLETE_NO})),
    }


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
