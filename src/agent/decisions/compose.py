"""Turn a Choice answer into the outcome Hermes code will honor."""

from __future__ import annotations

from agent.decisions.policy import ADVISORY_AUTO_MIN, ADVISORY_LOW, effective_outcome


def compose_choice(
    answer: dict[str, object],
    *,
    mode: str,
    binding: bool = False,
    irreversible: bool = False,
    auto_min: float = ADVISORY_AUTO_MIN,
    low: float = ADVISORY_LOW,
) -> tuple[str, str]:
    """Return `(proposed, effective)`. Shadow forces effective to `advise`."""
    proposed = propose_choice(
        answer,
        binding=binding,
        irreversible=irreversible,
        auto_min=auto_min,
        low=low,
    )
    return proposed, effective_outcome(mode, proposed)


def propose_choice(
    answer: dict[str, object],
    *,
    binding: bool,
    irreversible: bool,
    auto_min: float,
    low: float,
) -> str:
    choice = answer.get("choice")
    confidence = answer.get("confidence")
    if not isinstance(choice, str) or not isinstance(confidence, int | float):
        raise ValueError("Choice answer is incomplete")
    if irreversible:
        return "ask_person"
    if choice == "none":
        return "refuse" if binding else "advise"
    if float(confidence) < low:
        return "ask_person" if binding else "fallback_llm"
    if float(confidence) >= auto_min:
        return "run" if binding else "advise"
    return "ask_person" if binding else "fallback_llm"
