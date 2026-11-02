"""Named state for a System One request. Untrusted text stays in fields."""

from __future__ import annotations


def completion_state(request: str, skill_names: list[str]) -> dict[str, object]:
    """Place the caller prompt in `request`. Do not splice it into instructions."""
    return {"request": request, "skill_names": list(skill_names)}


def guard_state(text: str) -> dict[str, object]:
    """Place the screened message in `text`. Do not splice it into instructions."""
    return {"text": text}


def search_state(query: str, passages: list[dict[str, str]]) -> dict[str, object]:
    """Place the search query and passage text in named fields."""
    return {
        "query": query,
        "passages": [{"id": row["id"], "text": row["text"]} for row in passages],
    }


def memory_state(key: str, value: str) -> dict[str, object]:
    """Place the memory key and value in named fields."""
    return {"key": key, "value": value}


def supervisor_state(
    steps: list[dict[str, str]],
    evidence: list[dict[str, str]],
) -> dict[str, object]:
    """Place step records and code-gathered evidence in named fields."""
    return {
        "steps": [{"id": row["id"], "name": row["name"], "status": row["status"]} for row in steps],
        "evidence": [{"id": row["id"], "text": row["text"]} for row in evidence],
    }


def router_state(request: str) -> dict[str, object]:
    """Place the caller prompt in `request`. Do not splice it into instructions."""
    return {"request": request}


def tool_state(calls: list[dict[str, object]]) -> dict[str, object]:
    """Place proposed tool calls in named fields. Do not splice them into instructions."""
    return {"calls": calls}
