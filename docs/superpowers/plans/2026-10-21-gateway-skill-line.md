# Gateway Skill-Line Hook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose an MCP tool `suggest_skill` so `hermes-gateway` can obtain the same `<skill_relevance>` advisory line the API already builds, without changing the gateway LLM or `POST /completions` soft/shadow behavior.

**Architecture:** A small pure helper synthesizes `Skill` objects from a gateway-supplied roster, calls existing `suggest()` / `suggestion_block()`, and returns a JSON result. `api.mcp_tools` and `api.mcp_http` register and dispatch the tool. A SOUL paste doc tells the gateway when to call it. Roadmap #5 is marked done in docs only after the code ships.

**Tech Stack:** Python 3.12+, existing `skill_suggestion` pack, MCP streamable HTTP, pytest, stdlib `json` / `pathlib`.

## Global Constraints

- Do not set the gateway model to Jev / `jev-latest`.
- Do not change soft/shadow injection for `POST /completions` (completions still inject only in `soft`).
- No HTTP `POST /skills/suggest` in this phase.
- Default CI must not call TypeSafe; unit tests use a fake Jev client.
- Spec: `docs/superpowers/specs/2026-10-21-gateway-skill-line-design.md`.

## File map

| File | Role |
| --- | --- |
| `src/agent/decisions/gateway_skill_line.py` | Validate args; synthesize skills; run pack; build result dict |
| `tests/unit/test_gateway_skill_line.py` | Unit tests for the helper (fake Jev, no network) |
| `src/api/mcp_tools.py` | Dispatch `suggest_skill`; description constant; `MCP_TOOLS` entry |
| `src/api/mcp_http.py` | Register tool; update `MCP_TOOL_ORDER` and instructions |
| `tests/unit/test_mcp.py` | Expect six tools including `suggest_skill`; one call_tool smoke |
| `docs/architecture/gateway-skill-line-policy.md` | SOUL paste block for the gateway |
| `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md` | Mark #5 Done |
| `docs/architecture/jev-system-one.md` / `planned.md` | Hook exists; gateway LLM unchanged |
| `docs/changelogs/CHANGELOG.md` / `docs/testing/coverage.md` | One-liners |

---

### Task 1: Pure `suggest_skill` helper (TDD)

**Files:**
- Create: `src/agent/decisions/gateway_skill_line.py`
- Create: `tests/unit/test_gateway_skill_line.py`

**Interfaces:**
- Consumes: `suggest`, `suggestion_block`, `record_suggestion`, `PACK` from `agent.decisions.skill_suggestion`; `ACTIVE_PACKS` from `agent.decisions.packs`; `Skill` from `skills.loader`; `JevError` from `services.jev`
- Produces:
  - `suggest_skill_result(*, mode: str, client: object | None, settings_model: str, request: str, skills: list[dict[str, object]]) -> dict[str, object]`
  - Result keys: `available` (bool), `line` (str), `suggested` (str), `reason` (str), `model` (str)
  - Raises `ValueError` for blank `request`, empty/malformed `skills`, roster too large, or skill named `none`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_gateway_skill_line.py
from __future__ import annotations

import pytest

from agent.decisions.gateway_skill_line import suggest_skill_result
from agent.decisions.skill_suggestion import suggestion_block
from services.jev import JevError, JevResult


class _Jev:
    def __init__(self, answers: dict[str, object] | None = None, *, error: bool = False) -> None:
        self.answers = answers or {}
        self.error = error
        self.calls = 0

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        self.calls += 1
        if self.error:
            raise JevError("down")
        return JevResult(model="jev-1.13.0", answers=self.answers, usage={})


ROSTER = [
    {"name": "deploy", "description": "Promote the Hermes agent to production."},
    {"name": "ping", "description": "Reply with a short health word."},
]


def test_mode_off_is_unavailable_without_jev_call() -> None:
    client = _Jev()
    out = suggest_skill_result(
        mode="off",
        client=client,
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out == {
        "available": False,
        "line": "",
        "suggested": "",
        "reason": "unavailable",
        "model": "",
    }
    assert client.calls == 0


def test_empty_skills_raises_before_jev() -> None:
    client = _Jev()
    with pytest.raises(ValueError, match="skills"):
        suggest_skill_result(
            mode="shadow",
            client=client,
            settings_model="jev-1.13.0",
            request="hello",
            skills=[],
        )
    assert client.calls == 0


def test_shadow_returns_line_when_pack_picks_a_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.decisions import gateway_skill_line as mod

    class S:
        name = "deploy"
        reason = "ok"
        answers: dict[str, object] = {}
        model = "jev-1.13.0"

    monkeypatch.setattr(mod, "suggest", lambda client, request, skills: S())
    out = suggest_skill_result(
        mode="shadow",
        client=_Jev(),
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out["available"] is True
    assert out["suggested"] == "deploy"
    assert out["line"] == suggestion_block("deploy")
    assert out["reason"] == "ok"
    assert out["model"] == "jev-1.13.0"


def test_jev_error_returns_empty_line(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.decisions import gateway_skill_line as mod

    def boom(client: object, request: str, skills: list[object]) -> object:
        raise JevError("down")

    monkeypatch.setattr(mod, "suggest", boom)
    out = suggest_skill_result(
        mode="soft",
        client=_Jev(),
        settings_model="jev-1.13.0",
        request="deploy the agent",
        skills=ROSTER,
    )
    assert out["available"] is True
    assert out["line"] == ""
    assert out["suggested"] == ""
    assert out["reason"] == "jev_error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gateway_skill_line.py -q`  
Expected: FAIL (module missing)

- [ ] **Step 3: Implement the helper**

```python
# src/agent/decisions/gateway_skill_line.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gateway_skill_line.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/decisions/gateway_skill_line.py tests/unit/test_gateway_skill_line.py
git commit -m "feat: add gateway suggest_skill helper"
```

---

### Task 2: Wire MCP tool + registration

**Files:**
- Modify: `src/api/mcp_tools.py`
- Modify: `src/api/mcp_http.py`
- Modify: `tests/unit/test_mcp.py`

**Interfaces:**
- Consumes: `suggest_skill_result`, `encode_suggest_skill_result` from Task 1; `agent.settings`, `agent.jev`
- Produces: MCP tool name `suggest_skill` with args `request: str`, `skills: list[dict[str, str]]` (version optional per item)

- [ ] **Step 1: Extend `mcp_tools.py`**

Add to `MCP_TOOLS`:

```python
"suggest_skill": frozenset({"request", "skills"}),
```

Add description:

```python
SUGGEST_SKILL = (
    "Ask Hermes which gateway skill fits the latest user request. "
    "Pass the gateway's own skill names and short descriptions. "
    "Returns JSON with available, line, suggested, reason, and model. "
    "The line is advisory; the gateway model may ignore it."
)
```

In `call_tool`, before the generic string path:

```python
if name == "suggest_skill":
    return _suggest_skill(agent, arguments)
```

Implement:

```python
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
```

Import `SUGGEST_SKILL` in `mcp_http.py` alongside the other descriptions.

- [ ] **Step 2: Register in `mcp_http.py`**

Update instructions to mention skill suggestion. Add:

```python
@server.tool(name="suggest_skill", description=SUGGEST_SKILL, structured_output=False)
def suggest_skill(request: str, skills: list[dict[str, str]]) -> str:
    return call_tool(agent, "suggest_skill", {"request": request, "skills": skills})
```

Update:

```python
MCP_TOOL_ORDER = (
    "list_skills",
    "recall",
    "remember",
    "search_documents",
    "complete",
    "suggest_skill",
)
```

- [ ] **Step 3: Update `test_mcp.py` list assertion**

Change the five-tool test to six tools (alphabetical `tools/list` order):

```python
assert names == [
    "complete",
    "list_skills",
    "recall",
    "remember",
    "search_documents",
    "suggest_skill",
]
```

Rename the test if it says `five_tools`. Add a `call_tool` smoke with mode `off`:

```python
def test_suggest_skill_mode_off_returns_unavailable_json(tmp_path: Path) -> None:
    import json

    agent = _agent(tmp_path)  # jev mode defaults off
    raw = call_tool(
        agent,
        "suggest_skill",
        {
            "request": "deploy",
            "skills": [{"name": "deploy", "description": "Promote Hermes."}],
        },
    )
    payload = json.loads(raw)
    assert payload["available"] is False
    assert payload["line"] == ""
```

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_gateway_skill_line.py tests/unit/test_mcp.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/mcp_tools.py src/api/mcp_http.py tests/unit/test_mcp.py
git commit -m "feat: expose suggest_skill on MCP"
```

---

### Task 3: Gateway SOUL policy doc

**Files:**
- Create: `docs/architecture/gateway-skill-line-policy.md`

**Interfaces:**
- Consumes: tool contract from the design (`suggest_skill`, `hermes-api`)
- Produces: paste-ready SOUL block (no secrets)

- [ ] **Step 1: Write the policy doc**

Mirror the structure of `docs/architecture/shared-memory-policy.md`:

```markdown
# Gateway skill-line policy (standing instruction)

Paste the block below into the Hermes gateway identity file so Telegram (and dashboard chat) can ask the Python API for the same advisory skill line Hermes uses in soft completions.

**Where it lives on the server:** the gateway volume file `SOUL.md` under Hermes home (production Docker: inside `hermes-prod-gateway` at `/opt/data/SOUL.md`).

**Do not** put secrets, tokens, or host IPs in this policy. Tool names may use the MCP server name `hermes-api`.

---

## Skill suggestion (API)

When choosing among this gateway's skills for the user's latest message (or early in the turn when a skill might apply):

1. Call `hermes-api` tool `suggest_skill` with:
   - `request`: the user's latest message
   - `skills`: this gateway's roster as objects `{ "name", "description" }` (optional `version`)
2. Read the JSON result. If `available` is true and `line` is non-empty, treat `line` as advisory context for this turn. You may ignore it if it does not fit.
3. Do **not** replace this gateway's generative model with Jev. Hermes API remains the judge; you remain the agent.

If `available` is false or `line` is empty, continue without an advisory line.
```

- [ ] **Step 2: Commit**

```bash
git add docs/architecture/gateway-skill-line-policy.md
git commit -m "docs: add gateway skill-line SOUL policy"
```

---

### Task 4: Roadmap and architecture closeout

**Files:**
- Modify: `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md`
- Modify: `docs/architecture/jev-system-one.md`
- Modify: `docs/architecture/planned.md`
- Modify: `docs/changelogs/CHANGELOG.md`
- Modify: `docs/testing/coverage.md`

**Interfaces:**
- Consumes: shipped tool + policy paths from Tasks 2–3
- Produces: #5 marked Done; no claim that gateway LLM changed

- [ ] **Step 1: Update roadmap**

Mark row #5 **Done**. Add a Done bullet pointing at MCP `suggest_skill`, `docs/architecture/gateway-skill-line-policy.md`, and the design + this plan. Status line: steps 1–5 done for the hook; model switch still blocked if that note remains elsewhere.

- [ ] **Step 2: Update jev-system-one / planned**

Change the “Gateway skill line” later-improvement bullet to state the MCP hook exists; Nous gateway model unchanged; operator pastes SOUL from `gateway-skill-line-policy.md`.

- [ ] **Step 3: Changelog + coverage one-liners**

- Changelog: MCP `suggest_skill` returns the advisory skill line for gateway-supplied rosters; completions soft/shadow unchanged.
- Coverage: unit tests for `gateway_skill_line` + MCP registration of `suggest_skill`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md docs/architecture/jev-system-one.md docs/architecture/planned.md docs/changelogs/CHANGELOG.md docs/testing/coverage.md
git commit -m "docs: mark gateway skill-line hook done on the roadmap"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
| --- | --- |
| MCP tool `suggest_skill` | Task 2 |
| Gateway-supplied roster | Task 1–2 |
| Mode off → unavailable; shadow/soft return `line` | Task 1 |
| Reuse `suggest` / `suggestion_block` | Task 1 |
| Audit `suggestion_in_prompt=False` | Task 1 |
| SOUL paste doc | Task 3 |
| Unit tests, no live TypeSafe in CI | Task 1–2 |
| Roadmap / architecture closeout | Task 4 |
| No completion soft/shadow change | Global + no edits to `_skill_suggestion` inject path |
| No HTTP duplicate endpoint | Global |

No TBD/placeholder steps. Types: `suggest_skill_result` → JSON string via `encode_suggest_skill_result` → MCP text result.
