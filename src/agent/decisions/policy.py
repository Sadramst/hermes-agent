"""Mode and thresholds. Thresholds are plumbing knobs until a pack is promoted."""

from __future__ import annotations

# Unfitted plumbing knobs. Skill suggestion uses its own cookbook labels for shadow logs.
ADVISORY_AUTO_MIN = 0.90
ADVISORY_LOW = 0.40

# Tools that must not auto-run, at any Jev confidence. The runner asks a person instead.
IRREVERSIBLE_TOOLS: frozenset[str] = frozenset({"delete_memory"})


def effective_outcome(mode: str, proposed: str) -> str:
    """Shadow logs the proposal and leaves routing unchanged."""
    if mode == "off":
        return "fallback_llm"
    if mode == "shadow":
        return "advise"
    if mode == "soft":
        return proposed
    raise ValueError(f"Invalid Jev mode: {mode}")
