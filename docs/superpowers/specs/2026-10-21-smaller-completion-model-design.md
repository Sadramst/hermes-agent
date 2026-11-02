# Smaller completion model (router switch)

**Status:** shipped in `v0.3.9`; production soft with `HERMES_MODEL_SMALL` unset  
**Date:** 2026-10-21  
**Order:** Track 2 of follow-ups (after release hygiene; before soft promotion)  

**Prerequisite:** all-frontier comparison recorded (`tests/test_data/router/all-frontier-run.json`); gold still `plan`→frontier, `easy`→small  
**Parent:** [jev-system-one.md](../../architecture/jev-system-one.md) model router; [frontier-router-comparison-design.md](2026-10-21-frontier-router-comparison-design.md)

## Goal

When soft mode is on and a small model id is configured, use that model for completions the router labels `small`. Otherwise keep `HERMES_MODEL_NAME`. Shadow mode continues to **log only**.

## Non-goals

- Flipping production to `soft` (Track 3)
- Separate API keys / base URLs for the small model (reuse frontier provider credentials)
- Changing gold `tasks.json` or weakening the comparison artifact
- Per-pack soft flags

## Behavior

| Condition | Completion model |
| --- | --- |
| `HERMES_JEV_MODE` not `soft`, or no Jev client, or model-router pack inactive | `HERMES_MODEL_NAME` |
| soft + judge error / `none` / `unknown` / confidence-up → frontier | `HERMES_MODEL_NAME` |
| soft + `HERMES_MODEL_SMALL` empty/unset | `HERMES_MODEL_NAME` (switch disabled) |
| soft + `HERMES_MODEL_SMALL` set + judge returns tier `small` with reason `ok` | `HERMES_MODEL_SMALL` |

Fail **closed to frontier** whenever the small path is unclear.

Shadow and soft both still call `judge` / `record_route` as today for audit. Only soft may change which model id the generative client receives.

## Settings

- Add optional `HERMES_MODEL_SMALL` (string model id). Empty → treated as unset.
- Same `HERMES_MODEL_BASE_URL` and `HERMES_MODEL_API_KEY` as the frontier model.
- `GET /health` `model.name` remains the configured frontier name (`HERMES_MODEL_NAME`), not the per-request small id.

## Code touchpoints

- `utils/settings.py` — load `model_small`
- `agent/core.py` — `_model_route` (or `complete`) returns the chosen model id for this turn; pass it into the model client instead of always using settings frontier name
- Update `model_router` / `packs` comments: soft may switch when small is configured
- Unit tests with fake Jev / stubbed `judge`: soft+small, soft+unset small, soft+up, shadow never switches
- CHANGELOG + roadmap / planned note that switch exists but prod stays on shadow until soft promotion

## Success

- Unit tests prove soft switches only on `small`+`ok` with small configured.
- Prod can keep `HERMES_JEV_MODE=shadow` and behavior unchanged until Track 3.
- Comparison artifact remains the freeze line; no edit to weaken gold.

## Decisions

- Switch only in **soft**, with `HERMES_MODEL_SMALL` set, and judge `small`/`ok`.
- Fail closed to frontier otherwise.
