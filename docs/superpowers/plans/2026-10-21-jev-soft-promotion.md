# Jev Soft Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote production `HERMES_JEV_MODE` from `shadow` to `soft` with evidence, smoke, and rollback — no per-pack soft flags.

**Architecture:** Ops runbook against the live `5011-Hermes` stack. Code changes only if shadow-log evidence requires threshold edits (separate small PR). Prerequisites: release hygiene (Track 1) and smaller-model switch code (Track 2) merged; `HERMES_MODEL_SMALL` optional on day one.

**Tech Stack:** Docker Compose prod, `deploy.sh`, journal/docker logs, curl health, Telegram/MCP smoke.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-10-21-jev-soft-promotion-design.md`
- Global mode flip only — no `HERMES_JEV_SOFT_PACKS`
- `unset IMAGE_TAG` / use fixed `deploy.sh` before deploy
- Rollback = set `shadow` and redeploy in the same window if smoke fails
- Do not set gateway model to Jev

## File map

| File | Role |
| --- | --- |
| `docker/env/.env.prod` / `.env.agent` (server only) | `HERMES_JEV_MODE=soft` |
| Optional PR: pack threshold constants under `src/agent/decisions/` | Only if evidence demands |
| `docs/changelogs/CHANGELOG.md` / `jev-system-one.md` | Note prod soft after successful flip |
| `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md` | Optional status line |

---

### Task 1: Gather shadow evidence (operator + agent assist)

**Files:** none in git (log capture may be pasted into the task report under `.superpowers/sdd/`)

**Interfaces:**
- Consumes: docker logs for `hermes-agent` containing `jev.decision`
- Produces: short written summary (counts per pack, error rate, notable soft-would-have-changed events)

- [ ] **Step 1: Sample logs on prod**

```bash
cd /opt/hermes-agent
docker compose --env-file docker/env/.env.prod -f docker/docker-compose.prod.yml \
  logs hermes-agent --since 72h 2>/dev/null | grep 'jev.decision' | tail -n 200
```

If log volume is huge, narrow `--since 24h`.

- [ ] **Step 2: Summarize**

For each pack name seen (`skill-suggestion`, `chroma-passage`, `guardrails`, `memory-write`, `tool-call`, `model-router`, `supervisor`):

- approximate line count
- `reason=jev_error` count (if present in the log format)
- note any lines that show soft would withhold/hold/skip/inject

Write the summary to `.superpowers/sdd/soft-promotion-evidence.md` (gitignored scratch is fine) or the task report.

- [ ] **Step 3: Threshold gate**

If evidence shows systematic false soft actions that existing constants would enforce badly, open a **threshold PR** and **stop** this plan until it merges. Otherwise continue with existing constants.

- [ ] **Step 4: Commit** (only if a threshold PR is needed — else skip)

---

### Task 2: Preflight checklist

**Files:** none

- [ ] **Step 1: Confirm prerequisites**

```bash
# image includes Track 1+2
docker compose --env-file docker/env/.env.prod -f docker/docker-compose.prod.yml images hermes-agent
curl -sS http://127.0.0.1:8569/health
# expect jev.mode=shadow, version matches __version__ after Track 1 deploy
```

- [ ] **Step 2: Decide HERMES_MODEL_SMALL**

Either set a known-good small model id in `.env.prod` / `.env.agent`, or leave unset (soft completions stay on frontier). Record the choice in the evidence note.

- [ ] **Step 3: Confirm rollback command is ready**

```bash
# Will use after flip if smoke fails:
# set HERMES_JEV_MODE=shadow in env files, unset IMAGE_TAG, deploy.sh prod
```

---

### Task 3: Flip to soft + smoke + docs

**Files (after success):**
- Modify: `docs/changelogs/CHANGELOG.md`
- Modify: `docs/architecture/jev-system-one.md` (one sentence: this deployment runs soft)
- Optional: roadmap status line

- [ ] **Step 1: Flip env on server**

```bash
cd /opt/hermes-agent
# Edit docker/env/.env.prod and/or .env.agent so HERMES_JEV_MODE=soft
grep HERMES_JEV_MODE docker/env/.env.prod docker/env/.env.agent
unset IMAGE_TAG GHCR_OWNER
bash docker/scripts/deploy.sh prod
curl -sS http://127.0.0.1:8569/health
# expect "mode":"soft"
```

- [ ] **Step 2: Smoke checklist**

| Check | How | Expect |
| --- | --- | --- |
| Health | `curl …/health` | `jev.mode=soft` |
| Easy completion | `POST /completions` short prompt | 200, text present (or deliberate soft hold) |
| Plan-like completion | longer planning prompt | 200 |
| Search | `GET /documents/search?q=…` | 200 |
| Remember/recall | MCP or `/tools` | works |
| Telegram | new chat + skill question | `suggest_skill` still works |
| Guardrail sanity | known benign prompt | not falsely blocked |

If any critical check fails: **rollback to shadow immediately**, then stop and report.

- [ ] **Step 3: Docs commit (from a laptop branch after success)**

```bash
git add docs/changelogs/CHANGELOG.md docs/architecture/jev-system-one.md
git commit -m "docs: production Jev mode is soft"
```

- [ ] **Step 4: Report**

Status DONE with health JSON snippet and smoke results; or DONE_WITH_CONCERNS / rolled back.

---

## Spec coverage

| Spec item | Task |
| --- | --- |
| Evidence from shadow logs | Task 1 |
| Threshold PR if needed | Task 1 |
| Preflight Track 1+2 / MODEL_SMALL | Task 2 |
| Flip + smoke + rollback | Task 3 |
| Docs after success | Task 3 |

No TBD steps. Mode flip is env + deploy; code only for thresholds.
