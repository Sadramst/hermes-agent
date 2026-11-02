"""Allowlisted tool runner.

Hermes code checks the name and the argument keys, then runs the tool.
Irreversible tools ask a person and do not run. This module does not call Jev.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.decisions.policy import IRREVERSIBLE_TOOLS
from services.grok import GrokError, MAX_TASK_CHARS, REJECTED_TEXT

MAX_STEPS = 4

ASK_TEXT = "This tool needs a person before it can run."
GATE_TEXT = "This tool call was not run."
UNKNOWN_TEXT = "This tool is not on the allowlist."
ARGUMENTS_TEXT = "These arguments are outside the allowlist."
MISSING_TEXT = "No record is stored for that key."
EMPTY_SKILLS = "No skills are loaded."
OFF_TEXT = "Grok handoff is off."
TASK_TEXT = "This task is outside the allowlist."

# Argument keys Hermes may pass. Values stay out of logs.
TOOL_ARGUMENTS: dict[str, frozenset[str]] = {
    "recall": frozenset({"key"}),
    "remember": frozenset({"key", "value"}),
    "list_skills": frozenset(),
    "delete_memory": frozenset({"key"}),
    "delegate_to_grok": frozenset({"task"}),
}


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, str]


@dataclass(frozen=True)
class ToolResult:
    name: str
    status: str
    output: str


def run_calls(
    agent: object,
    calls: list[ToolCall],
    holds: list[str] | None = None,
) -> list[ToolResult]:
    """Run proposed calls in order. A batch past the step limit runs nothing.

    `holds` applies only to calls the allowlist would run. Irreversible tools
    still ask a person. Unknown names and bad arguments stay refused.
    """
    if len(calls) > MAX_STEPS:
        raise ValueError(f"A tool run is limited to {MAX_STEPS} calls")
    if holds is not None and len(holds) != len(calls):
        raise ValueError("Tool holds do not match the batch")
    results: list[ToolResult] = []
    for index, call in enumerate(calls):
        result = _stopped(agent, call)
        if result is None and holds is not None and holds[index] == "ask_person":
            result = ToolResult(call.name, "ask_person", ASK_TEXT)
        elif result is None and holds is not None and holds[index] == "refused":
            result = ToolResult(call.name, "refused", GATE_TEXT)
        elif result is None:
            result = _execute(agent, call)
        _log(agent, result)
        results.append(result)
    return results


def _stopped(agent: object, call: ToolCall) -> ToolResult | None:
    """Return a result when policy stops the call before it can run."""
    expected = TOOL_ARGUMENTS.get(call.name)
    if expected is None:
        return ToolResult(call.name, "refused", UNKNOWN_TEXT)
    if not _arguments_ok(call.arguments, expected):
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    if call.name == "delegate_to_grok":
        return _handoff_gate(agent, call)
    if call.name in IRREVERSIBLE_TOOLS:
        if not _key_ok(agent, call.arguments.get("key", "")):
            return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
        return ToolResult(call.name, "ask_person", ASK_TEXT)
    if call.name != "list_skills" and not _key_ok(agent, call.arguments["key"]):
        return ToolResult(call.name, "refused", ARGUMENTS_TEXT)
    return None


def _handoff_gate(agent: object, call: ToolCall) -> ToolResult | None:
    task = call.arguments["task"]
    if not task.strip() or len(task) > MAX_TASK_CHARS:
        return ToolResult(call.name, "refused", TASK_TEXT)
    mode = _handoff_mode(agent)
    if mode == "ask":
        return ToolResult(call.name, "ask_person", ASK_TEXT)
    if mode != "on":
        return ToolResult(call.name, "refused", OFF_TEXT)
    return None


def _handoff_mode(agent: object) -> str:
    settings = getattr(agent, "settings", None)
    mode = getattr(settings, "grok_handoff", "off")
    if mode not in {"off", "ask", "on"}:
        return "off"
    return mode


def _execute(agent: object, call: ToolCall) -> ToolResult:
    if call.name == "delegate_to_grok":
        return _delegate(agent, call)
    if call.name == "list_skills":
        return ToolResult(call.name, "ran", _skills(agent))
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


def _delegate(agent: object, call: ToolCall) -> ToolResult:
    send = getattr(agent, "delegate_to_grok", None)
    if not callable(send):
        return ToolResult(call.name, "refused", REJECTED_TEXT)
    try:
        handoff_id = send(call.arguments["task"])
    except GrokError:
        return ToolResult(call.name, "refused", REJECTED_TEXT)
    if not isinstance(handoff_id, str) or not handoff_id:
        return ToolResult(call.name, "refused", REJECTED_TEXT)
    return ToolResult(call.name, "ran", handoff_id)


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


def _log(agent: object, result: ToolResult) -> None:
    log = getattr(agent, "log", None)
    if log is None:
        return
    settings = getattr(agent, "settings", None)
    env = getattr(settings, "hermes_env", "")
    name = result.name if result.name in TOOL_ARGUMENTS else "unknown"
    log.info("tools.run name=%s status=%s env=%s", name, result.status, env)
