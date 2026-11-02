# MCP Soft Memory (Tool-Call Bypass) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Under soft mode, MCP `list_skills` / `recall` / `remember` call agent methods directly so soft tool-call cannot refuse them, while soft memory-write still returns `skipped` for one-shot chatter.

**Architecture:** Align the MCP memory trio with `search_documents` / `complete` / `suggest_skill`: `api.mcp_tools.call_tool` maps to `HermesAgent` methods and reuses the same output strings as `agent.tools` (`stored` / `skipped` / missing-key / skill lines). HTTP `POST /tools` keeps `run_tools` and soft `hold_for` unchanged.

**Tech Stack:** Python 3.12+, existing Jev soft packs, pytest, FastAPI MCP surface.

## Global Constraints

- Scope is MCP only; do not bypass soft tool-call for HTTP `/tools`.
- Soft memory-write stays enforced on `agent.remember` (MCP and `/tools`).
- No new env flags, key-prefix allowlists, or Jev packs.
- Spec: `docs/superpowers/specs/2026-10-21-mcp-soft-memory-design.md`.

## File map

| File | Role |
| --- | --- |
| `src/api/mcp_tools.py` | Route `list_skills` / `recall` / `remember` to agent methods; stop using `run_tools` for them |
| `tests/unit/test_mcp.py` | Soft-mode MCP tests: bypass tool-call; chatter → `skipped`; durable → `stored` + recall |
| `docs/architecture/shared-memory-policy.md` | One note: MCP memory trio skips soft tool-call, not soft memory-write |
| `docs/changelogs/CHANGELOG.md` | One bullet for the behavior change |

---

### Task 1: Soft MCP memory trio bypasses tool-call (TDD)

**Files:**
- Modify: `tests/unit/test_mcp.py`
- Modify: `src/api/mcp_tools.py`

**Interfaces:**
- Consumes: `HermesAgent.list_skills() -> list[Skill]`, `recall(key: str) -> str`, `remember(key: str, value: str) -> bool`; constants `EMPTY_SKILLS`, `MISSING_TEXT` from `agent.tools`
- Produces: `call_tool` returns the same strings as today’s tool runner for the trio, without calling `agent.run_tools`

- [ ] **Step 1: Write the failing soft bypass tests**

Add to `tests/unit/test_mcp.py` (imports: `JevError` already available via `services.jev` if needed; add `EMPTY_SKILLS`, `GATE_TEXT`, `MISSING_TEXT` from `agent.tools` only if asserted):

```python
class _QueueJev:
    """Fails closed if the tool-call pack is invoked; serves memory-write answers in order."""

    def __init__(self, memory_answers: list[dict[str, object]]) -> None:
        self.memory_answers = list(memory_answers)
        self.tool_calls = 0
        self.memory_calls = 0

    def evaluate(self, state: object, questions: dict[str, object]) -> JevResult:
        if "needs_tool" in questions:
            self.tool_calls += 1
            raise AssertionError("MCP memory trio must not run the tool-call pack")
        self.memory_calls += 1
        return JevResult(
            model="jev-1.13.0",
            answers=self.memory_answers[self.memory_calls - 1],
            usage={},
        )


def _memory_kept(kind: str = "fact", worth: float = 0.8) -> dict[str, object]:
    return {
        "worth": {"type": "noul", "noul": worth},
        "kind": {
            "type": "choice",
            "choice": kind,
            "probabilities": {kind: 0.8, "none": 0.2},
            "confidence": 0.7,
        },
    }


def _soft_agent(tmp_path: Path, jev: object) -> HermesAgent:
    _skill(tmp_path)
    settings = load_settings(
        _base(
            tmp_path,
            HERMES_MCP_ENABLED="on",
            HERMES_JEV_MODE="soft",
            HERMES_JEV_API_KEY="0123456789abcdef",
        )
    )
    return HermesAgent(
        settings,
        model_client=_Model(),
        chroma_client=_Chroma(),
        jev_client=jev,
    )


def test_soft_mcp_memory_trio_skips_tool_call_pack(tmp_path: Path) -> None:
    jev = _QueueJev([_memory_kept()])
    agent = _soft_agent(tmp_path, jev)
    assert "demo 0.1.0" in call_tool(agent, "list_skills", {})
    assert call_tool(agent, "remember", {"key": "note", "value": "durable fact for tomorrow"}) == "stored"
    assert call_tool(agent, "recall", {"key": "note"}) == "durable fact for tomorrow"
    assert jev.tool_calls == 0
    assert jev.memory_calls == 1


def test_soft_mcp_remember_still_skips_chatter(tmp_path: Path) -> None:
    jev = _QueueJev([_memory_kept(kind="none", worth=0.9)])
    agent = _soft_agent(tmp_path, jev)
    assert call_tool(agent, "remember", {"key": "ping", "value": "ok"}) == "skipped"
    assert call_tool(agent, "recall", {"key": "ping"}) == MISSING_TEXT
    assert jev.tool_calls == 0
    assert jev.memory_calls == 1
```

Import `MISSING_TEXT` from `agent.tools` at the top of the test module.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/unit/test_mcp.py::test_soft_mcp_memory_trio_skips_tool_call_pack tests/unit/test_mcp.py::test_soft_mcp_remember_still_skips_chatter -v
```

Expected: FAIL — soft `run_tools` path either refuses / asks a person, raises from `_QueueJev` when tool-call runs, or does not return `stored` / `skipped` as asserted.

- [ ] **Step 3: Implement direct agent dispatch in `mcp_tools.py`**

In `src/api/mcp_tools.py`:

1. Import `EMPTY_SKILLS`, `MISSING_TEXT` from `agent.tools` (keep existing `ARGUMENTS_TEXT`, `TOOL_ARGUMENTS` imports).
2. Add helpers (mirror `agent.tools` `_skills` / `_recall` / `_remember`):

```python
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
```

3. Change `call_tool` so after the `suggest_skill` branch and before/instead of `run_tools`:

```python
    if not _strings(arguments, MCP_TOOLS[name]):
        return ARGUMENTS_TEXT
    if name == "list_skills":
        return _list_skills(agent)
    if name == "recall":
        return _recall(agent, str(arguments["key"]))
    if name == "remember":
        return _remember(agent, str(arguments["key"]), str(arguments["value"]))
    return REFUSED_TEXT
```

Remove the `agent.run_tools([...])` call for these tools. After this change, no MCP tool should call `run_tools` (search/complete/suggest already have their own paths). Drop unused `ToolCall` import if nothing else needs it.

Keep `REMEMBER` description text that already mentions one-shot chatter may be skipped.

- [ ] **Step 4: Run the new tests and existing MCP smoke**

Run:

```bash
pytest tests/unit/test_mcp.py -v
```

Expected: PASS (including existing `test_tools_call_the_agent_and_refuse_unknown_arguments` and soft complete withhold).

- [ ] **Step 5: Confirm soft HTTP `/tools` still holds**

Run:

```bash
pytest tests/unit/test_tools.py::test_soft_refuses_when_jev_picks_none tests/unit/test_tools.py::test_soft_does_not_store_a_held_memory_write -v
```

Expected: PASS — soft `/tools` path unchanged.

- [ ] **Step 6: Commit**

```bash
git add src/api/mcp_tools.py tests/unit/test_mcp.py
git commit -m "$(cat <<'EOF'
fix: let MCP memory tools bypass soft tool-call hold

Soft mode was refusing Grok MCP remember/recall when Jev did not pick that tool. Route the MCP trio through agent methods like the other MCP tools, and keep soft memory-write.
EOF
)"
```

---

### Task 2: Document the soft MCP memory behavior

**Files:**
- Modify: `docs/architecture/shared-memory-policy.md`
- Modify: `docs/changelogs/CHANGELOG.md`

**Interfaces:**
- Consumes: behavior from Task 1
- Produces: operator-facing note + changelog bullet (no code API change)

- [ ] **Step 1: Add a short section to shared-memory-policy**

After the “Shared knowledge (API)” bullet list in `docs/architecture/shared-memory-policy.md`, add:

```markdown
## Soft mode (Jev)

When `HERMES_JEV_MODE=soft`, MCP `list_skills`, `recall`, and `remember` skip the soft **tool-call** hold so trusted MCP clients can use shared memory. Soft **memory-write** still applies: one-shot chatter on `remember` returns `skipped` and is not stored. HTTP `POST /tools` still enforces soft tool-call.
```

- [ ] **Step 2: Add a CHANGELOG bullet**

Near the top of the relevant unreleased / latest section in `docs/changelogs/CHANGELOG.md`, add one bullet:

```markdown
- Soft mode: MCP `list_skills`, `recall`, and `remember` call the agent directly (no soft tool-call hold). Soft memory-write still skips one-shot chatter (`skipped`). HTTP `POST /tools` is unchanged. See `docs/architecture/shared-memory-policy.md` and `docs/superpowers/specs/2026-10-21-mcp-soft-memory-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/shared-memory-policy.md docs/changelogs/CHANGELOG.md docs/superpowers/specs/2026-10-21-mcp-soft-memory-design.md docs/superpowers/plans/2026-10-21-mcp-soft-memory.md
git commit -m "$(cat <<'EOF'
docs: note MCP soft memory bypass for tool-call only

Operators need a clear line that MCP remember still honors soft chatter skip while soft tool-call no longer blocks the MCP path.
EOF
)"
```

(Include the design spec and this plan in the docs commit if they are still untracked.)

---

## Plan self-review

| Spec requirement | Task |
| --- | --- |
| MCP trio bypasses soft tool-call via direct agent methods | Task 1 |
| Soft memory-write still skips chatter (`skipped`) | Task 1 |
| HTTP `/tools` soft hold unchanged | Task 1 Step 5 |
| Docs note in shared-memory-policy | Task 2 |
| No new env / packs / always-store | Global constraints; no task adds them |

No placeholders left. Output strings match existing tool runner contracts.
