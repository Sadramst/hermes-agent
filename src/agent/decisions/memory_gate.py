"""Memory write gate pack v1.

Shadow logs whether a write looks like durable memory, and which kind.
Soft skips one-shot chatter. A Jev error still lets Hermes write.
Cookbook cutoffs are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import ChoiceQuestion, NoulQuestion, render_choice, render_noul
from agent.decisions.state import memory_state

PACK = "memory-write"
PACK_VERSION = "1"
EXCERPT_CHARS = 2000

# A worth noul below this is one-shot chatter. Exactly this value can keep.
# Shadow only logs that label. Soft skips the write.
WORTH_LABEL = 0.5

WORTH = "Is the text in `value` worth persisting as durable memory, rather than one-shot chatter?"
WORTH_YES = "It states a lasting fact, preference, or procedure that later work should still know."
WORTH_NO = "It is one-shot chatter, a status ping, or something that does not need to be kept."

KIND = "What kind of durable memory, if any, is the text in `value`?"
KINDS = {
    "fact": "A lasting fact about the user, their environment, or this system.",
    "preference": "A durable preference for how later work should be done.",
    "procedure": "A documented procedure or set of commands worth keeping.",
}
NONE_CRITERIA = "One-shot chatter. Not durable memory."


@dataclass(frozen=True)
class MemoryJudgment:
    kind: str
    reason: str
    answers: dict[str, Any]
    model: str


def judge(client: object, key: str, value: str) -> MemoryJudgment:
    """Ask once about one memory write. The caller still stores the full value."""
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    result = evaluate(memory_state(key, " ".join(value.split())[:EXCERPT_CHARS]), _questions())
    answers = _answers(result)
    kind, reason = label_memory(answers)
    model = getattr(result, "model", "")
    return MemoryJudgment(
        kind=kind,
        reason=reason,
        answers=answers,
        model=model if isinstance(model, str) else "",
    )


def label_memory(answers: dict[str, Any]) -> tuple[str, str]:
    """Return the kind to log, or an empty kind with the reason it was not kept."""
    worth = _noul(answers.get("worth"))
    which = answers.get("kind")
    if not isinstance(which, dict) or not isinstance(which.get("choice"), str):
        raise ValueError("Choice answer is incomplete")
    choice = which["choice"]
    if choice == "none":
        return "", "none"
    if choice not in KINDS:
        return "", "unknown"
    if worth < WORTH_LABEL:
        return "", "worth"
    return choice, "ok"


def record_memory(
    *,
    mode: str,
    model: str,
    memory_key: str,
    kind: str,
    answers: dict[str, Any],
    reason: str,
    persisted: bool,
    enforced: bool = False,
) -> dict[str, object]:
    """Log the judgment. The record keeps the key and omits the value."""
    if reason == "ok":
        proposed = "advise"
    elif reason == "jev_error":
        proposed = "fallback_llm"
    else:
        proposed = "refuse"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["key", "value"],
        answers=answers,
        proposed=proposed,
        effective=proposed if enforced else "advise",
        comparison={
            "memory_key": memory_key,
            "kind": kind,
            "reason": reason,
            "persisted": persisted,
            "enforced": enforced,
        },
    )


def _questions() -> dict[str, object]:
    criteria = {"none": NONE_CRITERIA, **KINDS}
    return {
        "worth": render_noul(NoulQuestion(WORTH, {"true": WORTH_YES, "false": WORTH_NO})),
        "kind": render_choice(ChoiceQuestion(KIND, criteria)),
    }


def _noul(answer: object) -> float:
    if not isinstance(answer, dict):
        raise ValueError("Noul answer is incomplete")
    value = answer.get("noul")
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Noul answer is incomplete")
    return float(value)


def _answers(result: object) -> dict[str, Any]:
    answers = getattr(result, "answers", None)
    if not isinstance(answers, dict):
        raise ValueError("Jev answer is incomplete")
    return answers
