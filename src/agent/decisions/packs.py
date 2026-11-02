"""Question packs. Instructions are fixed strings."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

# skill-suggestion may add a line in soft mode. chroma-passage may drop weak matches.
# guardrails withhold the model reply in soft mode. memory-write skips chatter in soft mode.
# tool-call logs in shadow. Soft mode can hold a call the allowlist would have run.
# model-router logs a tier. Soft may complete on HERMES_MODEL_SMALL when configured.
# supervisor logs in shadow. Soft mode stops calls that follow a looping judgment.
# The completion text stays unchanged. Step limits stay in code.
ACTIVE_PACKS: tuple[str, ...] = (
    "skill-suggestion",
    "chroma-passage",
    "guardrails",
    "memory-write",
    "tool-call",
    "model-router",
    "supervisor",
)


@dataclass(frozen=True)
class ChoiceQuestion:
    instructions: str
    criteria: Mapping[str, str]


def render_choice(question: ChoiceQuestion) -> dict[str, object]:
    """Return one Choice body. Reject a pack that cannot answer 'none'."""
    if "none" not in question.criteria:
        raise ValueError("Choice must include none")
    if not question.instructions.strip():
        raise ValueError("Choice instructions are empty")
    return {
        "type": "choice",
        "instructions": question.instructions,
        "criteria": dict(question.criteria),
    }


@dataclass(frozen=True)
class NoulQuestion:
    instructions: str | Mapping[str, object]
    criteria: Mapping[str, str] | None = None


def render_noul(question: NoulQuestion) -> dict[str, object]:
    """Return one Noul body. A mapping keeps the question text separate from its data."""
    instructions = question.instructions
    if isinstance(instructions, str):
        if not instructions.strip():
            raise ValueError("Noul instructions are empty")
        body: object = instructions
    elif isinstance(instructions, Mapping):
        question_text = instructions.get("question")
        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("Noul instructions are empty")
        body = dict(instructions)
    else:
        raise ValueError("Noul instructions are empty")
    rendered: dict[str, object] = {"type": "noul", "instructions": body}
    if question.criteria is not None:
        yes = question.criteria.get("true")
        no = question.criteria.get("false")
        if not isinstance(yes, str) or not yes.strip() or not isinstance(no, str) or not no.strip():
            raise ValueError("Noul criteria need true and false")
        rendered["criteria"] = {"true": yes, "false": no}
    return rendered


@dataclass(frozen=True)
class ScoreQuestion:
    instructions: str | Mapping[str, object]
    criteria: tuple[str, ...] | list[str]


def render_score(question: ScoreQuestion) -> dict[str, object]:
    """Return one Score body. Levels are ordered descriptions, low to high."""
    levels = list(question.criteria)
    if not 2 <= len(levels) <= 10:
        raise ValueError("Score needs 2 to 10 levels")
    if any(not isinstance(level, str) or not level.strip() for level in levels):
        raise ValueError("Score level is empty")
    instructions = question.instructions
    if isinstance(instructions, str):
        if not instructions.strip():
            raise ValueError("Score instructions are empty")
        body: object = instructions
    elif isinstance(instructions, Mapping):
        question_text = instructions.get("question")
        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError("Score instructions are empty")
        body = dict(instructions)
    else:
        raise ValueError("Score instructions are empty")
    return {"type": "score", "instructions": body, "criteria": levels}
