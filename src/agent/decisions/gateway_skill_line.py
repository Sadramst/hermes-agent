from __future__ import annotations

import json
from pathlib import Path

from agent.decisions.packs import ACTIVE_PACKS
from agent.decisions.skill_suggestion import (
    MAX_CHOICE_OPTIONS,
    PACK,
    record_suggestion,
    suggest,
    suggestion_block,
)
from services.jev import JevError
from skills.loader import Skill

GATEWAY_ROOT = Path("/gateway")


def suggest_skill_result(
    *,
    mode: str,
    client: object | None,
    settings_model: str,
    request: str,
    skills: list[dict[str, object]],
) -> dict[str, object]:
    """Return the MCP suggest_skill payload. Does not inject into completions."""
    text = request.strip()
    if not text:
        raise ValueError("request is required")
    roster = _skills_from_args(skills)
    if mode not in {"shadow", "soft"} or client is None or PACK not in ACTIVE_PACKS:
        return {
            "available": False,
            "line": "",
            "suggested": "",
            "reason": "unavailable",
            "model": "",
        }
    names = [skill.name for skill in roster]
    try:
        result = suggest(client, text, roster)
    except (JevError, ValueError):
        record_suggestion(
            mode=mode,
            model=settings_model,
            skill_names=names,
            answers={},
            suggested="",
            reason="jev_error",
            suggestion_in_prompt=False,
        )
        return {
            "available": True,
            "line": "",
            "suggested": "",
            "reason": "jev_error",
            "model": "",
        }
    suggested = result.name or ""
    reason = result.reason
    if suggested not in names:
        suggested = ""
        if result.name:
            reason = "unknown"
    offer_line = reason != "no_skills"
    line = suggestion_block(suggested or None) if offer_line else ""
    record_suggestion(
        mode=mode,
        model=result.model or settings_model,
        skill_names=names,
        answers=result.answers,
        suggested=suggested,
        reason=reason,
        suggestion_in_prompt=False,
    )
    return {
        "available": True,
        "line": line,
        "suggested": suggested,
        "reason": reason,
        "model": result.model or settings_model,
    }


def _skills_from_args(raw: list[dict[str, object]]) -> list[Skill]:
    if not raw:
        raise ValueError("skills must be a non-empty list")
    out: list[Skill] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each skill must be an object")
        name = str(item.get("name", "")).strip()
        description = str(item.get("description", "")).strip()
        if not name or not description:
            raise ValueError("each skill needs name and description")
        if name == "none":
            raise ValueError("Skill name collides with none")
        version = str(item.get("version") or "gateway").strip() or "gateway"
        out.append(
            Skill(
                name=name,
                version=version,
                path=GATEWAY_ROOT / name,
                body=description,
            )
        )
    if len(out) + 1 > MAX_CHOICE_OPTIONS:
        raise ValueError("Choice exceeds 255 options")
    return out


def encode_suggest_skill_result(payload: dict[str, object]) -> str:
    """JSON string for MCP tools that return unstructured text."""
    return json.dumps(payload, ensure_ascii=False)
