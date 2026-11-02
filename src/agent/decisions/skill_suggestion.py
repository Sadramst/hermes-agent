"""Skill suggestion pack v1.

Shadow logs the winner and leaves the completion prompt unchanged.
Soft mode adds one advisory block. The model may ignore it.
The cookbook cutoffs label that decision. They are not auto-run thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import ChoiceQuestion, NoulQuestion, render_choice, render_noul
from agent.decisions.policy import effective_outcome
from agent.decisions.state import completion_state
from agent.prompt import index_description
from skills.loader import Skill

PACK = "skill-suggestion"
PACK_VERSION = "1"

# Cookbook labels for the shadow log. Not auto-run thresholds.
SKILL_GATE_MIN = 0.30
SKILL_FITS_MIN = 0.30
SHORTLIST = 3
EXCERPT_CHARS = 700
MAX_CHOICE_OPTIONS = 255

NONE_CRITERIA = "No loaded skill fits the request."

WHICH = (
    "Which of these skills, if any, is the right one to load to help with the "
    "user's latest request?"
)
RERANK = (
    "Exactly one of these skills is the right one to load for the user's latest "
    "request. Which one? Read what each actually does, not just its name."
)
FITS_QUESTION = (
    "Does the skill in `candidate` do the specific thing the user's latest request asks for?"
)
ADVISORY_NONE = "No skill in the roster appears relevant to this request."

GATE_QUESTIONS = {
    "acts_on_user_system": (
        "Is the assistant being asked to act on the user's files, accounts, devices, "
        "or online services, rather than only to explain or advise?"
    ),
    "would_follow_documented_procedure": (
        "Would a careful expert answering this consult a specific documented procedure "
        "or set of commands, rather than answering from general understanding?"
    ),
    "prose_suffices": (
        "Could a knowledgeable generalist fully satisfy this request in prose, with "
        "no tools, no documentation, and no access to the user's files or accounts?"
    ),
}
INVERTED_GATES = frozenset({"prose_suffices"})


@dataclass(frozen=True)
class Suggestion:
    name: str | None
    reason: str
    answers: dict[str, Any]
    model: str


def suggest(client: object, request: str, skills: list[Skill]) -> Suggestion:
    """Return at most one skill name. An empty roster makes no Jev call."""
    if not skills:
        return Suggestion(name=None, reason="no_skills", answers={}, model="")
    unique = _unique_skills(skills)
    if any(skill.name == "none" for skill in unique):
        raise ValueError("Skill name collides with none")
    if len(unique) + 1 > MAX_CHOICE_OPTIONS:
        raise ValueError("Choice exceeds 255 options")
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    state = completion_state(request, [skill.name for skill in skills])
    wide = evaluate(state, _wide_questions(unique))
    wide_answers = _answers(wide)
    model = _model_name(wide)
    if _gate(wide_answers) < SKILL_GATE_MIN:
        return Suggestion(None, "gate", {"wide": wide_answers}, model)
    shortlist = _shortlist(wide_answers.get("which"), {skill.name for skill in unique})
    if not shortlist:
        return Suggestion(None, "no_shortlist", {"wide": wide_answers}, model)
    by_name = {skill.name: skill for skill in unique}
    rerank = evaluate(state, _rerank_questions(by_name, shortlist))
    rerank_answers = _answers(rerank)
    name, reason = _winner(rerank_answers, shortlist)
    return Suggestion(
        name,
        reason,
        {"wide": wide_answers, "rerank": rerank_answers},
        _model_name(rerank) or model,
    )


def suggestion_block(name: str | None) -> str:
    """One advisory block. A name is a loaded skill. An empty name says nothing fits."""
    if name:
        body = (
            f"Relevant to the current request: {name}. Ignore this if it does not fit "
            "what the user actually asked for."
        )
    else:
        body = ADVISORY_NONE
    return f"<skill_relevance>\n{body}\n</skill_relevance>"


def record_suggestion(
    *,
    mode: str,
    model: str,
    skill_names: list[str],
    answers: dict[str, Any],
    suggested: str,
    reason: str,
    suggestion_in_prompt: bool = False,
) -> dict[str, object]:
    """Log the comparison. The record keeps skill names and omits the request."""
    proposed = "advise" if suggested else "fallback_llm"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["request", "skill_names"],
        answers=answers,
        proposed=proposed,
        effective=effective_outcome(mode, proposed),
        comparison={
            "suggested": suggested,
            "reason": reason,
            "hermes_index": list(skill_names),
            "suggestion_in_prompt": suggestion_in_prompt,
        },
    )


def _wide_questions(skills: list[Skill]) -> dict[str, object]:
    criteria = {"none": NONE_CRITERIA}
    for skill in skills:
        criteria[skill.name] = index_description(skill.body)
    questions: dict[str, object] = {"which": render_choice(ChoiceQuestion(WHICH, criteria))}
    for key, text in GATE_QUESTIONS.items():
        questions[f"gate::{key}"] = render_noul(NoulQuestion(text))
    return questions


def _rerank_questions(by_name: dict[str, Skill], names: list[str]) -> dict[str, object]:
    criteria = {"none": NONE_CRITERIA}
    for name in names:
        criteria[name] = _rerank_text(by_name[name].body)
    questions: dict[str, object] = {"which": render_choice(ChoiceQuestion(RERANK, criteria))}
    for name in names:
        questions[f"fits::{name}"] = render_noul(
            NoulQuestion(
                {
                    "question": FITS_QUESTION,
                    "candidate": {"name": name, "description": criteria[name]},
                }
            )
        )
    return questions


def _rerank_text(body: str) -> str:
    return f"{index_description(body)} — {_excerpt(body)}"


def _excerpt(body: str) -> str:
    return " ".join(body.split())[:EXCERPT_CHARS]


def _unique_skills(skills: list[Skill]) -> list[Skill]:
    seen: set[str] = set()
    unique: list[Skill] = []
    for skill in skills:
        if skill.name in seen:
            continue
        seen.add(skill.name)
        unique.append(skill)
    return unique


def _gate(answers: dict[str, Any]) -> float:
    oriented: list[float] = []
    for key in GATE_QUESTIONS:
        value = _noul(answers.get(f"gate::{key}"))
        if key in INVERTED_GATES:
            value = 1.0 - value
        oriented.append(value)
    return sum(oriented) / len(oriented)


def _shortlist(which: object, known: set[str]) -> list[str]:
    if not isinstance(which, dict):
        raise ValueError("Choice answer is incomplete")
    probabilities = which.get("probabilities")
    if not isinstance(probabilities, dict):
        raise ValueError("Choice answer is incomplete")
    ranked: list[tuple[str, float]] = []
    for name, probability in probabilities.items():
        if (
            not isinstance(name, str)
            or isinstance(probability, bool)
            or not isinstance(probability, int | float)
        ):
            raise ValueError("Choice answer is incomplete")
        if name == "none" or name not in known:
            continue
        ranked.append((name, float(probability)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [name for name, _ in ranked[:SHORTLIST]]


def _winner(answers: dict[str, Any], shortlist: list[str]) -> tuple[str | None, str]:
    which = answers.get("which")
    if not isinstance(which, dict) or not isinstance(which.get("choice"), str):
        raise ValueError("Choice answer is incomplete")
    choice = which["choice"]
    fits = [_noul(answers.get(f"fits::{name}")) for name in shortlist]
    if choice == "none":
        return None, "none"
    if choice not in shortlist:
        return None, "unknown"
    if max(fits) < SKILL_FITS_MIN:
        return None, "fits"
    return choice, "ok"


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


def _model_name(result: object) -> str:
    model = getattr(result, "model", "")
    return model if isinstance(model, str) else ""
