"""Model router pack v1.

Shadow and soft log a tier for the next completion. Low confidence moves the
logged tier up to frontier. Soft mode may complete on HERMES_MODEL_SMALL when
the judge returns small with reason ok. Shadow always keeps HERMES_MODEL_NAME.
Cookbook probability cutoffs are not applied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.decisions.audit import audit_decision
from agent.decisions.packs import ChoiceQuestion, render_choice
from agent.decisions.state import router_state

PACK = "model-router"
PACK_VERSION = "1"

TIER = "Which model tier should answer the text in `request`?"
NONE_CRITERIA = "No smaller tier. Stay on the frontier model."
TIER_CRITERIA = {
    "frontier": "Planning, hard reasoning, or any turn that should stay on the frontier model.",
    "small": "A short, easy turn that does not need the frontier model.",
}

# Confidence at or below this is not enough to leave the frontier model.
# The logged tier moves up. It is not a vendor 0.90 cutoff.
CONFIDENCE_UP = 0.5


@dataclass(frozen=True)
class RouteJudgment:
    tier: str
    reason: str
    answers: dict[str, Any]
    model: str


def judge(client: object, request: str) -> RouteJudgment:
    """Ask once which tier fits this turn. The caller still picks the model."""
    evaluate = getattr(client, "evaluate", None)
    if not callable(evaluate):
        raise ValueError("Jev client has no evaluate")
    result = evaluate(router_state(request), _questions())
    answers = _answers(result)
    tier, reason = label_tier(answers)
    model = getattr(result, "model", "")
    return RouteJudgment(
        tier=tier,
        reason=reason,
        answers=answers,
        model=model if isinstance(model, str) else "",
    )


def label_tier(answers: dict[str, Any]) -> tuple[str, str]:
    """Return the tier to log. A small tier with low confidence moves up to frontier."""
    which = answers.get("tier")
    if not isinstance(which, dict) or not isinstance(which.get("choice"), str):
        raise ValueError("Choice answer is incomplete")
    choice = which["choice"]
    if choice == "none":
        return "frontier", "none"
    if choice not in TIER_CRITERIA:
        return "frontier", "unknown"
    if choice == "frontier":
        return "frontier", "ok"
    confidence = which.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        raise ValueError("Choice answer is incomplete")
    if float(confidence) <= CONFIDENCE_UP:
        return "frontier", "up"
    return "small", "ok"


def record_route(
    *,
    mode: str,
    model: str,
    tier: str,
    answers: dict[str, Any],
    reason: str,
) -> dict[str, object]:
    """Log the tier. The record omits the caller prompt."""
    proposed = "advise" if tier == "small" else "fallback_llm"
    return audit_decision(
        pack=PACK,
        pack_version=PACK_VERSION,
        mode=mode,
        model=model,
        state_fields=["request"],
        answers=answers,
        proposed=proposed,
        effective="advise",
        comparison={"tier": tier, "reason": reason, "enforced": False},
    )


def _questions() -> dict[str, object]:
    criteria = {"none": NONE_CRITERIA, **TIER_CRITERIA}
    return {"tier": render_choice(ChoiceQuestion(TIER, criteria))}


def _answers(result: object) -> dict[str, Any]:
    answers = getattr(result, "answers", None)
    if not isinstance(answers, dict):
        raise ValueError("Jev answer is incomplete")
    return answers
