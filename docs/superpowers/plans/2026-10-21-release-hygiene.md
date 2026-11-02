# Release Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `GET /health` report the package `__version__`, bump it to `0.3.8`, and make `deploy.sh` ignore stale shell `IMAGE_TAG` / `GHCR_OWNER`.

**Architecture:** Wire `_health_payload` to `agent.__version__` (stop hardcoding). Unset compose interpolation vars in `deploy.sh` before `docker compose`. Tag **v0.3.8** after merge.

**Tech Stack:** Python 3.12+, FastAPI TestClient, bash `deploy.sh`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-21-release-hygiene-design.md`
- Next release tag: **v0.3.8** with `__version__ = "0.3.8"`
- Do not add a separate health `image` field
- Do not change Compose service definitions except via deploy env interpolation behavior

## File map

| File | Role |
| --- | --- |
| `src/agent/__init__.py` | `__version__` bump |
| `src/agent/core.py` | `_health_payload` uses `__version__` |
| `tests/unit/test_health.py` | Assert health version matches `__version__` |
| `docker/scripts/deploy.sh` | `unset IMAGE_TAG GHCR_OWNER` before compose |
| `docs/changelogs/CHANGELOG.md` | 0.3.8 notes |

---

### Task 1: Health version from `__version__` (TDD)

**Files:**
- Modify: `src/agent/__init__.py`
- Modify: `src/agent/core.py` (`_health_payload`)
- Modify: `tests/unit/test_health.py`

**Interfaces:**
- Consumes: `from agent import __version__`
- Produces: health JSON `"version"` equals `__version__`

- [ ] **Step 1: Write the failing assertion**

In `tests/unit/test_health.py`, add to `test_health_reports_ok_environment_and_chroma_reachability` (or a new focused test):

```python
from agent import __version__

# inside the health test after body = response.json():
assert body["version"] == __version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_health.py::test_health_reports_ok_environment_and_chroma_reachability -q`  
Expected: FAIL — `body["version"]` is `"0.1.0"` while assertion may pass if `__version__` still `0.1.0`. First change the test to assert `body["version"] == __version__` and temporarily expect failure by asserting against a wrong constant, OR bump `__version__` first then fail until payload is fixed.

Preferred TDD order:

1. Change test to `assert body["version"] == __version__` (passes today while both are `0.1.0`).
2. Set `__version__ = "0.3.8"` — test **fails** (health still hardcoded `0.1.0`).
3. Fix `_health_payload` — test **passes**.

- [ ] **Step 3: Bump version and fix payload**

```python
# src/agent/__init__.py
__version__ = "0.3.8"
```

```python
# src/agent/core.py — top imports
from agent import __version__

# in _health_payload:
"version": __version__,
```

Remove the hardcoded `"0.1.0"` string.

- [ ] **Step 4: Run tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_health.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/__init__.py src/agent/core.py tests/unit/test_health.py
git commit -m "fix: report package __version__ on /health"
```

---

### Task 2: deploy.sh unsets shell IMAGE_TAG / GHCR_OWNER

**Files:**
- Modify: `docker/scripts/deploy.sh`

**Interfaces:**
- Consumes: existing compose `--env-file` path
- Produces: compose interpolation from env file only

- [ ] **Step 1: Edit deploy.sh**

After `ENV_FILE=...` is set and before any `docker compose` call, add:

```bash
# Shell exports override --env-file for Compose interpolation; always prefer the file.
unset IMAGE_TAG GHCR_OWNER
```

Place it once, shared by test/prod/dev branches (immediately before the `if [[ "${ENV_NAME}" == "test" ]]` block).

- [ ] **Step 2: Sanity check (manual)**

```bash
export IMAGE_TAG=v0.3.6
# dry-read: bash -n docker/scripts/deploy.sh
bash -n docker/scripts/deploy.sh
```

Expected: no syntax error. (Full pull test is optional on a machine with Docker.)

- [ ] **Step 3: Commit**

```bash
git add docker/scripts/deploy.sh
git commit -m "fix: ignore shell IMAGE_TAG when deploying"
```

---

### Task 3: Changelog for 0.3.8

**Files:**
- Modify: `docs/changelogs/CHANGELOG.md`

- [ ] **Step 1: Move / add release notes**

Under a new `## [0.3.8] - 2026-10-21` (or today’s date):

### Fixed
- `GET /health` reports `agent.__version__` instead of a hardcoded `0.1.0`.
- `deploy.sh` unsets shell `IMAGE_TAG` / `GHCR_OWNER` so Compose uses the env file.

Leave `## [Unreleased]` empty (or with a blank line).

- [ ] **Step 2: Commit**

```bash
git add docs/changelogs/CHANGELOG.md
git commit -m "docs: release notes for v0.3.8"
```

---

## Spec coverage

| Spec item | Task |
| --- | --- |
| `__version__` bump + health uses it | Task 1 |
| deploy.sh unset | Task 2 |
| Changelog / release tag v0.3.8 | Task 3 (+ tag after merge) |

After merge to main: `git tag -a v0.3.8 -m "v0.3.8"` and `git push origin v0.3.8` to run the release workflow; set `IMAGE_TAG=v0.3.8` on prod and deploy.
