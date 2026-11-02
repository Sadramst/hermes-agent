# Smaller Completion Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In soft mode, when `HERMES_MODEL_SMALL` is set and the model-router returns `small`/`ok`, call the generative API with that model id; otherwise keep `HERMES_MODEL_NAME`. Shadow stays log-only.

**Architecture:** Optional settings field `model_small`. `_model_route` returns the tier judgment; `complete()` picks the completion model id. `ModelClient.complete` accepts an optional per-call `model=` override. Fail closed to frontier.

**Tech Stack:** Python 3.12+, existing `model_router.judge`, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-21-smaller-completion-model-design.md`
- Switch **only** when `HERMES_JEV_MODE=soft` and `HERMES_MODEL_SMALL` non-empty and judge tier is `small` with reason `ok`
- Shadow never switches
- Fail closed to `HERMES_MODEL_NAME` on errors / up / unset small
- Same base URL and API key as frontier; no new provider secrets
- Do not flip prod to soft in this plan
- Do not edit gold `tasks.json` / comparison artifact

## File map

| File | Role |
| --- | --- |
| `src/utils/settings.py` | `model_small: str \| None` from `HERMES_MODEL_SMALL` |
| `src/services/model.py` | Optional `model=` on `complete()` |
| `src/agent/core.py` | Choose model id after route; pass into client |
| `src/agent/decisions/model_router.py` | Docstring update |
| `src/agent/decisions/packs.py` | Comment update |
| `tests/unit/test_settings.py` or existing settings tests | Load small model |
| `tests/unit/test_completions.py` or new `test_model_route_switch.py` | Soft switch / no-switch cases |
| `docs/changelogs/CHANGELOG.md` | Unreleased note |
| `docs/architecture/planned.md` / roadmap | Switch exists; soft still later |

---

### Task 1: Settings + ModelClient override (TDD)

**Files:**
- Modify: `src/utils/settings.py`
- Modify: `src/services/model.py`
- Modify: settings unit tests (find existing file under `tests/unit/` for settings — if none, add asserts in a small new test file `tests/unit/test_model_small_settings.py`)

**Interfaces:**
- Produces: `Settings.model_small: str | None`
- Produces: `ModelClient.complete(prompt: str, *, model: str | None = None) -> str`

- [ ] **Step 1: Failing settings test**

```python
# tests/unit/test_model_small_settings.py
from utils.settings import load_settings


def test_model_small_optional() -> None:
    base = {
        "HERMES_ENV": "test",
        "CHROMA_HOST": "chromadb",
    }
    off = load_settings(base)
    assert off.model_small is None
    on = load_settings({**base, "HERMES_MODEL_SMALL": "openrouter/cheap"})
    assert on.model_small == "openrouter/cheap"
```

- [ ] **Step 2: Run — expect FAIL (no attribute)**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_model_small_settings.py -q`

- [ ] **Step 3: Implement settings field**

Add `model_small: str | None` to `Settings`. In `load_settings`:

```python
raw_small = str(source.get("HERMES_MODEL_SMALL", "")).strip()
model_small = raw_small or None
```

Pass into `Settings(...)`.

- [ ] **Step 4: ModelClient override**

```python
def complete(self, prompt: str, *, model: str | None = None) -> str:
    status, body = self._json(
        {
            "model": model or self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
    )
    ...
```

Add a unit test in `tests/unit/test_model.py` that a fake opener sees payload model `other-model` when `complete(..., model="other-model")`.

- [ ] **Step 5: Run tests — PASS; commit**

```bash
git add src/utils/settings.py src/services/model.py tests/unit/test_model_small_settings.py tests/unit/test_model.py
git commit -m "feat: optional HERMES_MODEL_SMALL and per-call model override"
```

---

### Task 2: Wire soft switch in `complete()` (TDD)

**Files:**
- Modify: `src/agent/core.py`
- Modify: `src/agent/decisions/model_router.py` (docstrings only)
- Modify: `src/agent/decisions/packs.py` (comment)
- Create or extend: `tests/unit/test_model_route_switch.py`

**Interfaces:**
- Change `_model_route` to return `str` (completion model id to use), still recording the route
- Signature:

```python
def _model_route(
    *,
    mode: str,
    client: object | None,
    jev_model: str,
    request: str,
    frontier_name: str,
    small_name: str | None,
) -> str:
    """Log a tier. In soft mode may return small_name when the judge says small/ok."""
```

Logic:

```python
    if mode not in {"shadow", "soft"} or client is None or ROUTER_PACK not in ACTIVE_PACKS:
        return frontier_name
    try:
        result = judge_route(client, request)
    except (JevError, ValueError):
        record_route(mode=mode, model=jev_model, tier="frontier", answers={}, reason="jev_error")
        return frontier_name
    record_route(
        mode=mode,
        model=result.model or jev_model,
        tier=result.tier,
        answers=result.answers,
        reason=result.reason,
    )
    if (
        mode == "soft"
        and small_name
        and result.tier == "small"
        and result.reason == "ok"
    ):
        return small_name
    return frontier_name
```

In `HermesAgent.complete`, replace the current `_model_route(...); text = self.model.complete(checked)` with:

```python
        completion_model = _model_route(
            mode=self.settings.jev_mode,
            client=self.jev,
            jev_model=self.settings.jev_model,
            request=checked_prompt,
            frontier_name=self.settings.model_name or self.model.model,
            small_name=self.settings.model_small,
        )
        text = self.model.complete(checked, model=completion_model)
```

Use `completion_model` in the log `model.complete model=%s` lines for that turn (including held path keep frontier name as today).

- [ ] **Step 1: Failing agent tests**

Use a recording model client:

```python
class _Model:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.models: list[str | None] = []
        self.model = "frontier-model"

    def complete(self, prompt: str, *, model: str | None = None) -> str:
        self.prompts.append(prompt)
        self.models.append(model)
        return "ok"
```

Monkeypatch `judge_route` to return a `RouteJudgment(tier="small", reason="ok", answers={}, model="jev")`.

Cases:
1. soft + `HERMES_MODEL_SMALL=cheap` + small/ok → `models[-1] == "cheap"`
2. soft + no small env → `"frontier-model"` (or settings name)
3. shadow + small env + small/ok → frontier (no switch)
4. soft + reason `up` → frontier

- [ ] **Step 2: RED then implement then GREEN**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_model_route_switch.py -q`

- [ ] **Step 3: Update docs comments in model_router.py and packs.py**

- [ ] **Step 4: Commit**

```bash
git add src/agent/core.py src/agent/decisions/model_router.py src/agent/decisions/packs.py tests/unit/test_model_route_switch.py
git commit -m "feat: soft mode may complete on HERMES_MODEL_SMALL"
```

---

### Task 3: Docs closeout

**Files:**
- Modify: `docs/changelogs/CHANGELOG.md` (Unreleased)
- Modify: `docs/architecture/planned.md` and/or `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md`
- Modify: `docs/architecture/jev-system-one.md` one sentence under model router

- [ ] **Step 1: Document** that soft may switch when `HERMES_MODEL_SMALL` is set; prod remains shadow until soft promotion.

- [ ] **Step 2: Commit**

```bash
git add docs/changelogs/CHANGELOG.md docs/architecture/planned.md docs/architecture/jev-system-one.md docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md
git commit -m "docs: note soft smaller-model switch"
```

---

## Spec coverage

| Spec item | Task |
| --- | --- |
| `HERMES_MODEL_SMALL` | Task 1 |
| Per-call model override | Task 1 |
| Soft-only switch + fail closed | Task 2 |
| Shadow unchanged | Task 2 |
| Docs | Task 3 |
