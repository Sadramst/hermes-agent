"""MCP tool dispatch. Policy stays in the agent methods this module calls."""

from __future__ import annotations

from collections.abc import Callable

from agent.core import HermesAgent
from agent.tools import ARGUMENTS_TEXT, EMPTY_SKILLS, MISSING_TEXT, TOOL_ARGUMENTS
from services.chroma import ChromaError
from services.embedder import EmbeddingError
from services.model import ModelError, ModelNotConfigured

MCP_TOOLS: dict[str, frozenset[str]] = {
    "list_skills": TOOL_ARGUMENTS["list_skills"],
    "recall": TOOL_ARGUMENTS["recall"],
    "remember": TOOL_ARGUMENTS["remember"],
    "search_documents": frozenset({"q", "limit"}),
    "search_memory": frozenset({"q", "limit"}),
    "complete": frozenset({"prompt"}),
    "suggest_skill": frozenset({"request", "skills"}),
}

REFUSED_TEXT = "This tool is not on the MCP server."
NO_MATCHES = "No documents matched."
NO_MEMORY_MATCHES = "No memory records matched."
CHROMA_TEXT = "Chroma request failed"
EMBEDDING_TEXT = "Embedding request failed"
MODEL_MISSING = "Model provider is not configured"
MODEL_FAILED = "Model request failed"

LIST_SKILLS = "List the skills Hermes has loaded."
RECALL = "Read one Hermes memory record by key."
REMEMBER = "Store one Hermes memory record. One-shot chatter may be skipped."
SEARCH_DOCUMENTS = (
    "Search documents Hermes has saved: runbooks, infrastructure notes, and reference text. "
    "Each result starts with a [label] line; cite that label when you use the passage."
)
SEARCH_MEMORY = (
    "Search Hermes memory records by meaning when you do not know the exact key. "
    "Each result names the key; call recall with it for the full record."
)
COMPLETE = "Ask Hermes for one completion. Hermes uses its own model, not Cursor's."
SUGGEST_SKILL = (
    "Ask Hermes which gateway skill fits the latest user request. "
    "Pass the gateway's own skill names and short descriptions. "
    "Returns JSON with available, line, suggested, reason, and model. "
    "The line is advisory; the gateway model may ignore it."
)


def call_tool(agent: HermesAgent, name: str, arguments: dict[str, object]) -> str:
    """Run one MCP tool. Unknown names and bad argument keys are refused."""
    if name not in MCP_TOOLS:
        return REFUSED_TEXT
    if name == "search_documents":
        return _search(agent, arguments)
    if name == "search_memory":
        return _search_memory(agent, arguments)
    if name == "complete":
        return _complete(agent, arguments)
    if name == "suggest_skill":
        return _suggest_skill(agent, arguments)
    if not _strings(arguments, MCP_TOOLS[name]):
        return ARGUMENTS_TEXT
    if name == "list_skills":
        return _list_skills(agent)
    if name == "recall":
        return _recall(agent, str(arguments["key"]))
    if name == "remember":
        return _remember(agent, str(arguments["key"]), str(arguments["value"]))
    return REFUSED_TEXT


def _list_skills(agent: HermesAgent) -> str:
    lines = [
        f"{skill.name} {skill.version}"
        for skill in agent.list_skills()
        if isinstance(getattr(skill, "name", None), str)
    ]
    return "\n".join(lines) if lines else EMPTY_SKILLS


def _recall(agent: HermesAgent, key: str) -> str:
    try:
        text = agent.recall(key)
    except FileNotFoundError:
        return MISSING_TEXT
    return text if isinstance(text, str) else MISSING_TEXT


def _remember(agent: HermesAgent, key: str, value: str) -> str:
    return "stored" if agent.remember(key, value) else "skipped"


def _strings(arguments: dict[str, object], expected: frozenset[str]) -> bool:
    if set(arguments) != expected:
        return False
    return all(isinstance(arguments[key], str) for key in expected)


def _search(agent: HermesAgent, arguments: dict[str, object]) -> str:
    payload = _run_search(agent.search_documents, "search_documents", arguments)
    if isinstance(payload, str):
        return payload
    lines: list[str] = []
    for match in _rows(payload):
        label = match.get("id")
        text = match.get("text")
        if isinstance(label, str) and isinstance(text, str):
            lines.append(f"{_heading(label, match)}\n{text}")
    return "\n\n".join(lines) if lines else NO_MATCHES


def _search_memory(agent: HermesAgent, arguments: dict[str, object]) -> str:
    payload = _run_search(agent.search_memory, "search_memory", arguments)
    if isinstance(payload, str):
        return payload
    lines: list[str] = []
    for match in _rows(payload):
        key = match.get("key")
        text = match.get("text")
        if isinstance(key, str) and isinstance(text, str):
            lines.append(f"key={key}\n{text}")
    return "\n\n".join(lines) if lines else NO_MEMORY_MATCHES


def _run_search(
    search: Callable[[str, int], dict[str, object]],
    name: str,
    arguments: dict[str, object],
) -> dict[str, object] | str:
    keys = set(arguments)
    if "q" not in keys or not keys <= MCP_TOOLS[name]:
        return ARGUMENTS_TEXT
    query = arguments["q"]
    limit = arguments.get("limit", 5)
    if not isinstance(query, str) or isinstance(limit, bool) or not isinstance(limit, int):
        return ARGUMENTS_TEXT
    try:
        return search(query, limit)
    except ValueError as exc:
        return str(exc)
    except ChromaError:
        return CHROMA_TEXT
    except EmbeddingError:
        return EMBEDDING_TEXT


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return []
    return [match for match in matches if isinstance(match, dict)]


def _heading(label: str, match: dict[str, object]) -> str:
    parts = [f"[{label}]"]
    source_id = match.get("source_id")
    if isinstance(source_id, str) and source_id != label:
        parts.append(f"doc={source_id}")
    source = match.get("source")
    if isinstance(source, str) and source:
        parts.append(f"source={source}")
    return " ".join(parts)


def _complete(agent: HermesAgent, arguments: dict[str, object]) -> str:
    if set(arguments) != MCP_TOOLS["complete"]:
        return ARGUMENTS_TEXT
    prompt = arguments["prompt"]
    if not isinstance(prompt, str):
        return ARGUMENTS_TEXT
    try:
        result = agent.complete(prompt)
    except ValueError as exc:
        return str(exc)
    except ModelNotConfigured:
        return MODEL_MISSING
    except ModelError:
        return MODEL_FAILED
    text = result.get("text")
    return text if isinstance(text, str) else ""


def _suggest_skill(agent: HermesAgent, arguments: dict[str, object]) -> str:
    from agent.decisions.gateway_skill_line import (
        encode_suggest_skill_result,
        suggest_skill_result,
    )

    if set(arguments) != MCP_TOOLS["suggest_skill"]:
        return ARGUMENTS_TEXT
    request = arguments["request"]
    skills = arguments["skills"]
    if not isinstance(request, str) or not isinstance(skills, list):
        return ARGUMENTS_TEXT
    try:
        payload = suggest_skill_result(
            mode=agent.settings.jev_mode,
            client=agent.jev,
            settings_model=agent.settings.jev_model,
            request=request,
            skills=skills,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        return str(exc)
    return encode_suggest_skill_result(payload)
