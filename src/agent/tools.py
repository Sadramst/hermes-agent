"""Allowlisted tool runner and OpenAI-compatible tool definitions for the autonomous loop.

Hermes checks tool names and exact argument keys, then executes read/write actions.
Irreversible tools (`delete_memory`) pause for human confirmation (`ask_person`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from services.chroma import ChromaError
from services.embedder import EmbeddingError
from utils.time import now_report

MAX_STEPS = 4
IRREVERSIBLE_TOOLS: frozenset[str] = frozenset({"delete_memory"})

ASK_TEXT = "This tool needs a person before it can run."
UNKNOWN_TEXT = "This tool is not on the allowlist."
ARGUMENTS_TEXT = "These arguments are outside the allowlist."
MISSING_TEXT = "No record is stored for that key."
EMPTY_SKILLS = "No skills are loaded."
MISSING_SKILL = "No skill is loaded with that name."
EMPTY_MEMORIES = "No memory records matched."
NO_DOCUMENTS = "No documents matched."
NO_MEMORIES = "No memory records matched."
SEARCH_FAILED = "Search failed."
SAVE_FAILED = "Document save failed."

# Argument keys Hermes may pass. Values stay out of logs.
TOOL_ARGUMENTS: dict[str, frozenset[str]] = {
    "recall": frozenset({"key"}),
    "remember": frozenset({"key", "value"}),
    "list_memories": frozenset({"prefix"}),
    "list_skills": frozenset(),
    "read_skill": frozenset({"name"}),
    "search_documents": frozenset({"q"}),
    "save_document": frozenset({"id", "text"}),
    "search_memory": frozenset({"q"}),
    "current_time": frozenset(),
    "delete_memory": frozenset({"key"}),
}

AGENT_TOOL_SCHEMAS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": "Read a stored memory record by its exact key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "Memory key to read."}},
                "required": ["key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Save a durable fact or note into Hermes persistent memory under a stable dotted key.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short dotted memory key (e.g. 'goal.weekly', 'finance.budget', 'work.project')."},
                    "value": {"type": "string", "description": "Fact or note text to store."},
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "List stored memory keys, optionally filtered by key prefix (e.g. 'finance.', 'goal.', or '' for all).",
            "parameters": {
                "type": "object",
                "properties": {
                    "prefix": {
                        "type": "string",
                        "description": "Optional prefix such as 'finance.' or 'goal.'; pass '' for all keys.",
                    }
                },
                "required": ["prefix"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "Search stored memory records by meaning or keyword when the exact key is unknown.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string", "description": "Search query for memory."}},
                "required": ["q"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search ChromaDB knowledge base documents for relevant passages and [label] citations.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string", "description": "Search query."}},
                "required": ["q"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_document",
            "description": "Chunk, embed, and store a document in the ChromaDB knowledge base.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Stable document ID."},
                    "text": {"type": "string", "description": "Document text content."},
                },
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List all loaded Hermes skills and their versions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_skill",
            "description": "Read the full instructions of a loaded Hermes skill by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Name of the skill."}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Return the current date, local time in the configured timezone, UTC ISO timestamp, weekday, and ISO week.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, str]


@dataclass(frozen=True)
class ToolResult:
    name: str
    status: str
    output: str


def run_calls(agent: object, calls: list[ToolCall]) -> list[ToolResult]:
    """Run allowlisted calls in order. A batch past MAX_STEPS runs nothing."""
    if len(calls) > MAX_STEPS:
        raise ValueError(f"A tool run is limited to {MAX_STEPS} calls")
    results: list[ToolResult] = []
    for call in calls:
        result = _stopped(agent, call) or _execute(agent, call)
        _log(agent, result)
        results.append(result)
    return results


def _stopped(agent: object, call: ToolCall) -> ToolResult | None:
    expected = TOOL_ARGUMENTS.get(call.name)
    if expected is None:
        return ToolResult(call.name, "refused", UNKNOWN_TEXT)
    if not _arguments_ok(call.arguments, expected):
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    if call.name in IRREVERSIBLE_TOOLS:
        if not _key_ok(agent, call.arguments.get("key", "")):
            return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
        return ToolResult(call.name, "ask_person", ASK_TEXT)
    if call.name in {"recall", "remember"} and not _key_ok(agent, call.arguments["key"]):
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    if call.name in {"search_documents", "search_memory"} and not call.arguments["q"].strip():
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    if call.name == "read_skill" and not call.arguments["name"].strip():
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    if call.name == "save_document" and (
        not call.arguments["id"].strip() or not call.arguments["text"].strip()
    ):
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    return None


def _execute(agent: object, call: ToolCall) -> ToolResult:
    if call.name == "list_skills":
        return ToolResult(call.name, "ran", _skills(agent))
    if call.name == "read_skill":
        return ToolResult(call.name, "ran", _read_skill(agent, call.arguments["name"]))
    if call.name == "list_memories":
        return ToolResult(call.name, "ran", _list_memories(agent, call.arguments["prefix"]))
    if call.name == "current_time":
        return ToolResult(call.name, "ran", _current_time(agent))
    if call.name == "search_documents":
        return ToolResult(call.name, "ran", _search_documents(agent, call.arguments["q"]))
    if call.name == "save_document":
        return _save_document(agent, call.arguments["id"], call.arguments["text"])
    if call.name == "search_memory":
        return ToolResult(call.name, "ran", _search_memory(agent, call.arguments["q"]))
    key = call.arguments["key"]
    if call.name == "recall":
        return ToolResult(call.name, "ran", _recall(agent, key))
    return ToolResult(call.name, "ran", _remember(agent, key, call.arguments["value"]))


def _arguments_ok(arguments: object, expected: frozenset[str]) -> bool:
    if not isinstance(arguments, dict) or set(arguments) != expected:
        return False
    return all(isinstance(value, str) for value in arguments.values())


def _key_ok(agent: object, key: str) -> bool:
    memory = getattr(agent, "memory", None)
    check = getattr(memory, "check", None)
    if not callable(check):
        return False
    try:
        check(key)
    except ValueError:
        return False
    return True


def _recall(agent: object, key: str) -> str:
    recall = getattr(agent, "recall")
    try:
        text = recall(key)
    except FileNotFoundError:
        return MISSING_TEXT
    return text if isinstance(text, str) else MISSING_TEXT


def _remember(agent: object, key: str, value: str) -> str:
    remember = getattr(agent, "remember")
    kept = remember(key, value)
    return "stored" if kept else "skipped"


def _list_memories(agent: object, prefix: str) -> str:
    list_fn = getattr(agent, "list_memories", None)
    if callable(list_fn):
        keys = list_fn(prefix)
    else:
        memory = getattr(agent, "memory", None)
        keys_fn = getattr(memory, "keys", None)
        if not callable(keys_fn):
            return EMPTY_MEMORIES
        cleaned = prefix.strip()
        keys = [k for k in keys_fn() if not cleaned or k.startswith(cleaned)]
    return "\n".join(keys[:50]) if keys else EMPTY_MEMORIES


def _current_time(agent: object) -> str:
    now_fn = getattr(agent, "current_time", None)
    if callable(now_fn):
        return json.dumps(now_fn(), sort_keys=True)
    settings = getattr(agent, "settings", None)
    tz_name = getattr(settings, "timezone", "UTC")
    return json.dumps(now_report(tz_name), sort_keys=True)


def _skills(agent: object) -> str:
    list_skills = getattr(agent, "list_skills")
    skills = list_skills()
    lines = [
        f"{skill.name} {skill.version}"
        for skill in skills
        if isinstance(getattr(skill, "name", None), str)
    ]
    if not lines:
        return EMPTY_SKILLS
    return "\n".join(lines)


def _read_skill(agent: object, name: str) -> str:
    list_skills = getattr(agent, "list_skills", None)
    if not callable(list_skills):
        return MISSING_SKILL
    target = name.strip()
    for skill in list_skills():
        if getattr(skill, "name", None) == target:
            body = getattr(skill, "body", "")
            return str(body).strip() if body else f"{target} ({getattr(skill, 'version', '0.0.0')})"
    return MISSING_SKILL


def _search_documents(agent: object, query: str) -> str:
    search = getattr(agent, "search_documents", None)
    if not callable(search):
        return SEARCH_FAILED
    try:
        payload = search(query, 5)
    except (ChromaError, EmbeddingError, ValueError):
        return SEARCH_FAILED
    matches = payload.get("matches") if isinstance(payload, dict) else None
    if not isinstance(matches, list) or not matches:
        return NO_DOCUMENTS
    lines: list[str] = []
    for match in matches:
        if isinstance(match, dict):
            label = match.get("id")
            text = match.get("text")
            if isinstance(label, str) and isinstance(text, str):
                lines.append(f"[{label}]\n{text}")
    return "\n\n".join(lines) if lines else NO_DOCUMENTS


def _save_document(agent: object, doc_id: str, text: str) -> ToolResult:
    save = getattr(agent, "save_document", None)
    if not callable(save):
        return ToolResult("save_document", "refused", SAVE_FAILED)
    try:
        result = save(doc_id, text)
    except ValueError:
        return ToolResult("save_document", "refused", ARGUMENTS_TEXT)
    except (ChromaError, EmbeddingError):
        return ToolResult("save_document", "refused", SAVE_FAILED)
    chunks = result.get("chunks", 0) if isinstance(result, dict) else 0
    return ToolResult("save_document", "ran", f"saved id={doc_id} chunks={chunks}")


def _search_memory(agent: object, query: str) -> str:
    search = getattr(agent, "search_memory", None)
    if callable(search):
        try:
            payload = search(query, 5)
            matches = payload.get("matches") if isinstance(payload, dict) else None
            if isinstance(matches, list):
                lines = [
                    f"key={row['key']}\n{row['text']}"
                    for row in matches
                    if isinstance(row, dict)
                    and isinstance(row.get("key"), str)
                    and isinstance(row.get("text"), str)
                ]
                return "\n\n".join(lines) if lines else NO_MEMORIES
        except ValueError:
            pass
        except (ChromaError, EmbeddingError):
            return SEARCH_FAILED
    memory = getattr(agent, "memory", None)
    keys_fn = getattr(memory, "keys", None)
    read_fn = getattr(memory, "read", None)
    if not (callable(keys_fn) and callable(read_fn)):
        return NO_MEMORIES
    terms = [term.lower() for term in query.split() if term.strip()]
    found: list[str] = []
    for key in keys_fn():
        try:
            val = read_fn(key)
        except OSError:
            continue
        haystack = f"{key} {val}".lower()
        if not terms or any(term in haystack for term in terms):
            found.append(f"key={key}\n{val}")
            if len(found) >= 5:
                break
    return "\n\n".join(found) if found else NO_MEMORIES


def _log(agent: object, result: ToolResult) -> None:
    log = getattr(agent, "log", None)
    if log is None:
        return
    settings = getattr(agent, "settings", None)
    env = getattr(settings, "hermes_env", "")
    name = result.name if result.name in TOOL_ARGUMENTS else "unknown"
    log.info("tools.run name=%s status=%s env=%s", name, result.status, env)
