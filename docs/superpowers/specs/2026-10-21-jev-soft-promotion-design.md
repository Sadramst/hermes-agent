# Jev soft promotion (global mode)

**Status:** done on production (2026-10-21) — `HERMES_JEV_MODE=soft` on `v0.3.9`; `HERMES_MODEL_SMALL` deferred  

**Date:** 2026-10-21  
**Order:** Track 3 of follow-ups (after release hygiene and smaller-model switch code)  
**Parent:** [jev-system-one.md](../../architecture/jev-system-one.md) modes and promotion rules

## Goal

Promote production from `HERMES_JEV_MODE=shadow` to `soft` with shadow-log evidence, threshold confirmation, a smoke checklist, and an explicit rollback — **without** adding per-pack soft flags.

## Non-goals

- Per-pack soft env (`HERMES_JEV_SOFT_PACKS=…`)
- Replacing the Nous gateway LLM
- Demoting individual packs while leaving others soft
- Requiring `HERMES_MODEL_SMALL` on day one (optional; if unset, soft completions stay on frontier)

## Blast radius

Flipping global mode to `soft` activates soft behavior for every pack that already implements it:

| Pack | Soft effect |
| --- | --- |
| skill-suggestion | Injects `<skill_relevance>` on API completions |
| chroma-passage | May drop weak search neighbors |
| guardrails | May withhold replies on `review` / `block` |
| memory-write | May skip one-shot writes |
| tool-call | May hold unclear tool calls |
| supervisor | May stop looping tool batches |
| model-router | May use `HERMES_MODEL_SMALL` when Track 2 is shipped and the env is set |

## Procedure

1. **Evidence** — On prod, sample recent `jev.decision` audit lines by pack. Record approximate volume, `jev_error` rate, and how often soft *would* have changed the outcome (propose ≠ effective / suggestion_in_prompt / holds).
2. **Thresholds** — Confirm named constants already in code (skill gates, `CONFIDENCE_UP`, guardrail routes, passage helping level, etc.) are acceptable. If not, land a small PR to adjust **before** the flip.
3. **Preflight** — Track 1 (hygiene) and Track 2 (switch code) merged and tagged as needed. Decide whether `HERMES_MODEL_SMALL` is set on day one.
4. **Flip** — Set `HERMES_JEV_MODE=soft` in the prod env files Hermes reads (`docker/env/.env.prod` and/or `.env.agent` as this deployment uses). Run `deploy.sh prod` with a clean shell (`unset IMAGE_TAG`). Confirm `GET /health` → `jev.mode=soft`.
5. **Smoke** — Completions (easy + plan-like prompts), document search, remember/recall, `POST /tools`, Telegram/MCP including `suggest_skill`.
6. **Rollback** — Set mode back to `shadow`, redeploy; verify health and that completions again return text on soft-only holds.

## Deliverables

- This design (ops runbook).
- Implementation plan with checklist steps and where to look for logs.
- Optional: short section in `docs/architecture/jev-system-one.md` / CHANGELOG noting production soft after the flip.
- Code PR only if thresholds must change; the mode flip itself is env + deploy.

## Success

- Prod health reports `jev.mode=soft`.
- Smoke checklist passes or rollback is executed within the same change window.
- No silent IMAGE_TAG override during the deploy.

## Decisions

- Global soft flip (ops + verification), not per-pack soft.
- Thresholds from existing code unless evidence demands a PR first.
