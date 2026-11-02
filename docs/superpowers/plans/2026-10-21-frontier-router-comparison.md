# Frontier Router Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Commit a live-recorded `all-frontier-run.json` that proves the model-router labels match `tasks.json` gold tiers, plus an offline CI check — without switching completion models.

**Architecture:** Extract small pure helpers to load gold tasks, turn a `RouteJudgment` into one artifact row, and assert a run file matches gold. An opt-in script builds a real `JevClient` from env, calls `judge()` per task, and writes the artifact. Default pytest only reads the committed files (no network).

**Tech Stack:** Python 3.12+, existing `JevClient` / `model_router.judge`, pytest, stdlib `json` / `pathlib`.

## Global Constraints

- No `HERMES_MODEL_SMALL`; do not change `HermesAgent.complete()` model selection.
- Do not call `POST /completions` in the recorder.
- Default CI must not call TypeSafe; live recording is opt-in and requires `HERMES_JEV_API_KEY`.
- Pass rule: for every task in `tasks.json`, `logged_tier == gold_tier` (`tier` field). Confidence/reason are audit-only.
- Artifact path: `tests/test_data/router/all-frontier-run.json`.
- Spec: `docs/superpowers/specs/2026-10-21-frontier-router-comparison-design.md`.

## File map

| File | Role |
| --- | --- |
| `src/agent/decisions/frontier_comparison.py` | Load gold tasks; build one task record; assert run matches gold |
| `tests/unit/test_frontier_comparison.py` | Unit tests for helpers (inline fixtures, no live Jev) |
| `scripts/record_frontier_router_run.py` | Live opt-in recorder → writes artifact |
| `tests/test_data/router/all-frontier-run.json` | Committed live recording |
| `tests/unit/test_frontier_run_artifact.py` | Offline CI: real gold + artifact paths |
| `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md` | Mark #4 comparison recorded |
| `docs/architecture/planned.md` / `jev-system-one.md` | Note comparison artifact exists; switch still later |

---

### Task 1: Pure comparison helpers (TDD)

**Files:**
- Create: `src/agent/decisions/frontier_comparison.py`
- Create: `tests/unit/test_frontier_comparison.py`

**Interfaces:**
- Consumes: `agent.decisions.model_router.RouteJudgment` (or tier/reason/confidence fields)
- Produces:
  - `load_gold_tasks(path: Path) -> list[dict[str, str]]` — each item has `id`, `tier`, `prompt`
  - `task_record(*, task_id: str, prompt: str, gold_tier: str, logged_tier: str, reason: str, confidence: float | None) -> dict[str, object]`
  - `assert_run_matches_gold(run: dict[str, object], gold_tasks: list[dict[str, str]]) -> None` — raises `AssertionError` on mismatch/missing/duplicate ids

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_frontier_comparison.py
from pathlib import Path

import pytest

from agent.decisions.frontier_comparison import (
    assert_run_matches_gold,
    load_gold_tasks,
    task_record,
)


def test_load_gold_tasks_reads_frozen_file() -> None:
    root = Path(__file__).resolve().parents[1]
    tasks = load_gold_tasks(root / "test_data" / "router" / "tasks.json")
    assert [t["id"] for t in tasks] == ["plan", "easy"]
    assert tasks[0]["tier"] == "frontier"
    assert tasks[1]["tier"] == "small"


def test_task_record_sets_match() -> None:
    row = task_record(
        task_id="easy",
        prompt="Reply with the word pong.",
        gold_tier="small",
        logged_tier="small",
        reason="ok",
        confidence=0.9,
    )
    assert row["match"] is True
    assert row["logged_tier"] == "small"


def test_assert_run_matches_gold_passes_and_fails() -> None:
    gold = [
        {"id": "plan", "tier": "frontier", "prompt": "p"},
        {"id": "easy", "tier": "small", "prompt": "e"},
    ]
    good = {
        "tasks": [
            task_record(
                task_id="plan",
                prompt="p",
                gold_tier="frontier",
                logged_tier="frontier",
                reason="ok",
                confidence=None,
            ),
            task_record(
                task_id="easy",
                prompt="e",
                gold_tier="small",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
        ]
    }
    assert_run_matches_gold(good, gold)

    bad = {
        "tasks": [
            task_record(
                task_id="plan",
                prompt="p",
                gold_tier="frontier",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
            task_record(
                task_id="easy",
                prompt="e",
                gold_tier="small",
                logged_tier="small",
                reason="ok",
                confidence=0.9,
            ),
        ]
    }
    with pytest.raises(AssertionError, match="plan"):
        assert_run_matches_gold(bad, gold)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_frontier_comparison.py -q`
Expected: FAIL (module / functions missing)

- [ ] **Step 3: Implement helpers**

```python
# src/agent/decisions/frontier_comparison.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_gold_tasks(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    tasks = data["tasks"]
    out: list[dict[str, str]] = []
    for item in tasks:
        out.append(
            {
                "id": str(item["id"]),
                "tier": str(item["tier"]),
                "prompt": str(item["prompt"]),
            }
        )
    return out


def task_record(
    *,
    task_id: str,
    prompt: str,
    gold_tier: str,
    logged_tier: str,
    reason: str,
    confidence: float | None,
) -> dict[str, object]:
    return {
        "id": task_id,
        "prompt": prompt,
        "gold_tier": gold_tier,
        "logged_tier": logged_tier,
        "reason": reason,
        "confidence": confidence,
        "match": logged_tier == gold_tier,
    }


def assert_run_matches_gold(run: dict[str, object], gold_tasks: list[dict[str, str]]) -> None:
    raw = run.get("tasks")
    if not isinstance(raw, list):
        raise AssertionError("run.tasks must be a list")
    by_id: dict[str, dict[str, object]] = {}
    for row in raw:
        if not isinstance(row, dict) or "id" not in row:
            raise AssertionError("each run task needs an id")
        tid = str(row["id"])
        if tid in by_id:
            raise AssertionError(f"duplicate task id {tid}")
        by_id[tid] = row
    for gold in gold_tasks:
        tid = gold["id"]
        if tid not in by_id:
            raise AssertionError(f"missing task id {tid}")
        row = by_id[tid]
        logged = str(row.get("logged_tier"))
        gold_tier = gold["tier"]
        if logged != gold_tier:
            raise AssertionError(f"{tid}: logged_tier {logged!r} != gold {gold_tier!r}")
        if str(row.get("gold_tier")) != gold_tier:
            raise AssertionError(f"{tid}: gold_tier field != tasks.json")
    if len(by_id) != len(gold_tasks):
        raise AssertionError("run has extra task ids")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_frontier_comparison.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/decisions/frontier_comparison.py tests/unit/test_frontier_comparison.py
git commit -m "feat: add frontier router comparison helpers"
```

---

### Task 2: Live recorder script

**Files:**
- Create: `scripts/record_frontier_router_run.py`

**Interfaces:**
- Consumes: `load_gold_tasks`, `task_record`, `judge` from `model_router`, `JevClient`, `load_settings`
- Produces: writes `tests/test_data/router/all-frontier-run.json`; exit `0` if every `match` is true, else exit `1` (still write the file)

- [ ] **Step 1: Implement the recorder**

```python
# scripts/record_frontier_router_run.py
"""Opt-in live recording of model-router tiers for tests/test_data/router/tasks.json.

Requires HERMES_JEV_API_KEY. Does not call the generative model.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.decisions.frontier_comparison import load_gold_tasks, task_record  # noqa: E402
from agent.decisions.model_router import judge  # noqa: E402
from services.jev import JevClient  # noqa: E402
from utils.settings import load_settings  # noqa: E402

TASKS_PATH = ROOT / "tests" / "test_data" / "router" / "tasks.json"
OUT_PATH = ROOT / "tests" / "test_data" / "router" / "all-frontier-run.json"


def main() -> int:
    settings = load_settings()
    if not settings.jev_api_key:
        print("HERMES_JEV_API_KEY is required", file=sys.stderr)
        return 2
    client = JevClient(settings.jev_base_url, settings.jev_model, settings.jev_api_key)
    gold = load_gold_tasks(TASKS_PATH)
    rows: list[dict[str, object]] = []
    jev_model = settings.jev_model
    for task in gold:
        judgment = judge(client, task["prompt"])
        confidence = None
        tier_answer = judgment.answers.get("tier")
        if isinstance(tier_answer, dict):
            raw = tier_answer.get("confidence")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool):
                confidence = float(raw)
        if judgment.model:
            jev_model = judgment.model
        rows.append(
            task_record(
                task_id=task["id"],
                prompt=task["prompt"],
                gold_tier=task["tier"],
                logged_tier=judgment.tier,
                reason=judgment.reason,
                confidence=confidence,
            )
        )
    payload = {
        "note": "All-frontier router comparison. Completions were not switched to a smaller model.",
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "jev_model": jev_model,
        "tasks": rows,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    mismatches = [r["id"] for r in rows if not r["match"]]
    if mismatches:
        print(f"tier mismatch for: {mismatches}", file=sys.stderr)
        return 1
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke without a key**

Run: `.\.venv\Scripts\python.exe scripts/record_frontier_router_run.py`
Expected: exit `2`, stderr contains `HERMES_JEV_API_KEY is required`

- [ ] **Step 3: Commit**

```bash
git add scripts/record_frontier_router_run.py
git commit -m "feat: add opt-in frontier router recording script"
```

---

### Task 3: Record live artifact + offline CI test

**Files:**
- Create: `tests/test_data/router/all-frontier-run.json` (via live script)
- Create: `tests/unit/test_frontier_run_artifact.py`

**Interfaces:**
- Consumes: committed artifact + `assert_run_matches_gold` / `load_gold_tasks`
- Produces: green offline CI gate

- [ ] **Step 1: Run the live recorder**

From a shell that has production-equivalent Jev env (e.g. after `set -a; source docker/env/.env.prod; set +a` on a machine with the key, or export `HERMES_JEV_API_KEY` locally):

```bash
cd /path/to/hermes-agent
# HERMES_ENV may be prod/dev; chroma host must satisfy load_settings — use a minimal env:
# HERMES_ENV=dev CHROMA_HOST=localhost HERMES_JEV_API_KEY=... HERMES_JEV_MODE=shadow
.\.venv\Scripts\python.exe scripts/record_frontier_router_run.py
```

Expected: exit `0`, file `tests/test_data/router/all-frontier-run.json` exists, both tasks `match: true`.

If exit `1` (tier mismatch), stop and report — do not weaken gold tiers.

- [ ] **Step 2: Write the offline artifact test**

```python
# tests/unit/test_frontier_run_artifact.py
import json
from pathlib import Path

from agent.decisions.frontier_comparison import assert_run_matches_gold, load_gold_tasks

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "test_data" / "router" / "tasks.json"
RUN = ROOT / "test_data" / "router" / "all-frontier-run.json"


def test_committed_all_frontier_run_matches_gold_tiers() -> None:
    gold = load_gold_tasks(GOLD)
    run = json.loads(RUN.read_text(encoding="utf-8"))
    assert_run_matches_gold(run, gold)
```

- [ ] **Step 3: Run offline tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_frontier_comparison.py tests/unit/test_frontier_run_artifact.py -q`
Expected: PASS (no network)

- [ ] **Step 4: Commit**

```bash
git add tests/test_data/router/all-frontier-run.json tests/unit/test_frontier_run_artifact.py
git commit -m "test: commit all-frontier router run matching gold tiers"
```

---

### Task 4: Docs and roadmap closeout

**Files:**
- Modify: `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md`
- Modify: `docs/architecture/jev-system-one.md` (Later improvements §1)
- Modify: `docs/architecture/planned.md`
- Modify: `docs/changelogs/CHANGELOG.md` (Unreleased or next patch note)
- Modify: `docs/testing/coverage.md` (one line on the artifact check)

- [ ] **Step 1: Update roadmap**

Mark #4 as **Done (comparison recorded; model switch still blocked)** and add a Done bullet pointing at `tests/test_data/router/all-frontier-run.json` and the recorder script. Link the design + this plan.

- [ ] **Step 2: Update jev-system-one / planned**

State that the all-frontier router recording exists; selecting a smaller completion model remains a later PR.

- [ ] **Step 3: Changelog + coverage one-liners**

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md docs/architecture/jev-system-one.md docs/architecture/planned.md docs/changelogs/CHANGELOG.md docs/testing/coverage.md
git commit -m "docs: record frontier router comparison on the roadmap"
```

---

## Spec coverage (self-review)

| Spec requirement | Task |
| --- | --- |
| Live opt-in script + `HERMES_JEV_API_KEY` | Task 2–3 |
| Write `all-frontier-run.json` | Task 2–3 |
| Call `judge` only / no completions | Task 2 |
| Offline CI checks gold tiers | Task 1 + 3 |
| No model switch | Global constraints |
| Artifact fields (id, gold, logged, reason, confidence, match) | Task 1 `task_record` |
| Roadmap update | Task 4 |

No TBD/placeholder steps. Types consistent: `task_record` → artifact rows → `assert_run_matches_gold`.
