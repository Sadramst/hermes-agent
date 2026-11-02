# Gateway skill-line hook (MCP)

**Status:** approved design  
**Date:** 2026-10-21  
**Roadmap:** shared-knowledge #5  
**Parent:** [jev-system-one.md](../../architecture/jev-system-one.md) § Later improvements (gateway skill line); [shared-knowledge-roadmap.md](2026-10-21-shared-knowledge-roadmap.md)

## Goal

Give the Nous `hermes-gateway` a control-plane way to obtain the same advisory `<skill_relevance>` line the Python API already builds for soft completions — without replacing the gateway’s generative model or changing `HERMES_MODEL_NAME`.

## Non-goals

- Setting the gateway model to Jev / `jev-latest`
- Changing soft/shadow injection behavior for `POST /completions` (completions still inject only in `soft`)
- A duplicate HTTP `POST /skills/suggest` in this phase
- Auto-injecting into the gateway prompt from the API (the gateway chooses whether to use `line`)
- Rebuilding the Nous gateway image for this feature

## Approach

**Thin MCP tool + existing `suggest()` pack.**

Add `suggest_skill` on the existing Python API `/mcp` surface (next to `remember` / `recall` / `list_skills`). The gateway passes its own skill roster; the API runs the skill-suggestion pack against that roster and returns the advisory `line`. Operator guidance is a paste block for gateway `SOUL.md`, same pattern as [shared-memory-policy.md](../../architecture/shared-memory-policy.md).

## Tool contract

**Name:** `suggest_skill`  
**Auth:** same bearer as other MCP tools (`HERMES_API_TOKEN`).

### Arguments

| Arg | Type | Notes |
| --- | --- | --- |
| `request` | string | Latest user message; required, non-empty |
| `skills` | array | Gateway roster. Each item: `name` (required), `description` (required; used as skill body for the pack/index), optional `version` (default `"gateway"`) |

Reject an empty `skills` array with a structured validation error (no TypeSafe call). Cap roster size so named skills + the pack’s `none` option stay within the Choice limit (≤255 options total).

### Result fields

| Field | Meaning |
| --- | --- |
| `available` | `false` when `HERMES_JEV_MODE` is `off`, Jev is not configured, or the skill-suggestion pack is inactive |
| `line` | Full `<skill_relevance>…</skill_relevance>` text when the pack succeeds and a block should be offered; otherwise `""` |
| `suggested` | Winning skill name, or `""` |
| `reason` | Same family as today’s pack (`ok`, `no_skills`, `jev_error`, validation reasons, …) |
| `model` | Jev model id when a call ran; otherwise `""` |

### Mode behavior (differs from completions)

| Mode | Completions (`HermesAgent.complete`) | This MCP tool |
| --- | --- | --- |
| `off` | No Jev call | `available: false`, `line: ""`, no TypeSafe call |
| `shadow` | Pack runs; **no** prompt injection | Pack runs; **returns** `line` when the pack succeeds so the gateway can inject |
| `soft` | Pack runs; injects advisory block | Pack runs; returns `line` the same way |

Audit logs may reuse `record_suggestion` (or an equivalent) with `suggestion_in_prompt=false` for MCP calls — the gateway owns injection.

### Errors

- Jev / pack `ValueError`: `available: true`, `line: ""`, `reason: jev_error` (or a specific validation reason). Do not fail the gateway closed.
- Missing/blank `request` or empty `skills`: structured validation error, no TypeSafe call.

### Implementation notes

- Synthesize `Skill` instances from MCP args: `name`, `version`, a dummy `path` (e.g. `Path("/gateway") / name`), `body=description`.
- Call existing `agent.decisions.skill_suggestion.suggest` and `suggestion_block`.
- Register the tool in `src/api/mcp_http.py` and `src/api/mcp_tools.py`, and include it in `MCP_TOOL_ORDER`.

## Gateway SOUL policy

New doc at `docs/architecture/gateway-skill-line-policy.md`:

- Paste into gateway `SOUL.md` (`hermes-prod-gateway` volume `/opt/data/SOUL.md` on production).
- Instruct: when choosing among skills (or early in a turn), call `hermes-api` `suggest_skill` with the user request and this gateway’s skill names + one-line descriptions.
- If `line` is non-empty, treat it as advisory context (may ignore).
- Do not replace the gateway LLM with Jev. Do not put secrets in SOUL.
- Tool names may use the MCP server name `hermes-api`.

## Testing

- Unit tests with a fake Jev client: expected `line` / `suggested`; mode `off` → `available: false`; empty skills → validation; Jev error → empty `line` + `jev_error`.
- Assert MCP registration exposes `suggest_skill`.
- Default CI must not call TypeSafe.

## Rollout

1. Ship API image including `suggest_skill` (normal version/tag bump).
2. Paste SOUL policy on the production gateway; confirm MCP server `hermes-api` is already connected.
3. Smoke from Telegram or dashboard: a turn that should prefer a known skill; confirm the tool is used and/or the advisory line is respected.
4. Mark roadmap #5 Done; update `jev-system-one.md` / `planned.md` that the hook exists.

## Success criteria

- Gateway can obtain the same-shaped `<skill_relevance>` line from the API using its own roster.
- Nous gateway generative model unchanged.
- `POST /completions` soft/shadow behavior unchanged.
- Default CI stays offline for TypeSafe.

## Decisions locked in brainstorming

1. Delivery: MCP tool on the Python API (not HTTP-only, not SOUL-only).
2. Roster: gateway-supplied in the tool args.
3. Mode: return `line` in both `shadow` and `soft` when the pack succeeds; `off` → unavailable.
4. Adoption: SOUL paste block (no gateway image skill required for this phase).
