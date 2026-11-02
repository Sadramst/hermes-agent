# Shared knowledge across gateways — feature roadmap

**Status:** steps 1–5 done; soft on production (`v0.3.10`); soft MCP memory + handoff MCP writeback verified; gateway skill-line SOUL applied; `HERMES_MODEL_SMALL` deferred (unset)

**Date:** 2026-10-21  
**Context:** Grok and Telegram both call the Python Hermes API over MCP. Bidirectional `remember` / `recall` works. The gateway still has its own memory tools, which caused the Telegram note about two stores.

## Goal

Every gateway and client that should share facts uses one library: the Python API (`hermes-agent` on port 8569 / `https://api.hermes.newplanetit.com.au`). Memory files, Chroma documents, and Jev gates stay there.

## Done

- MCP enabled on the API; public host `api.hermes.newplanetit.com.au`
- Grok Bot connected with bearer `HERMES_API_TOKEN`
- Gateway MCP server `hermes-api` at `http://hermes-agent:8080/mcp/` (Docker DNS; public URL timed out from inside the gateway)
- `HERMES_MCP_ALLOWED_HOSTS` includes `api.hermes.newplanetit.com.au` and `hermes-agent`
- Telegram recalled `grok-test`; Grok recalled `grok-test-new`
- Telegram SOUL shared-memory policy applied; unprompted remember key `office-wifi-hint` readable from Grok
- Grok handoff loop live: `HERMES_GROK_HANDOFF=on`, hosted `hermes-grok-agent`; channel writes `grok-result-<handoffId>` via Hermes MCP `remember` (not `POST /tools`) so soft tool-call cannot refuse writeback
- Soft MCP memory: API `list_skills` / `recall` / `remember` bypass soft tool-call (`v0.3.10`); soft memory-write still skips chatter
- Production soft e2e on `v0.3.10` (2026-10-21): Grok MCP `remember`/`recall` round-trip; `delegate_to_grok` → `recall grok-result-<id>` returned `FLOW-OK:…`
- Production API on `HERMES_JEV_MODE=soft` (`GET /health` → `jev.mode=soft`, `jev.configured=true`, model `jev-1.13.0` on `v0.3.10`); `HERMES_MODEL_SMALL` unset day one
- Frontier router comparison recorded: `tests/test_data/router/all-frontier-run.json` from `scripts/record_frontier_router_run.py` matches the frozen tasks; soft may use `HERMES_MODEL_SMALL` when set, shadow stays log-only
- Gateway skill-line hook exposed as MCP `suggest_skill`; production gateway `SOUL.md` includes `docs/architecture/gateway-skill-line-policy.md`. See the gateway skill-line design and plan.

## Ordered work

| # | Feature | Kind | Why next |
| --- | --- | --- | --- |
| 1 | Telegram prefers shared API memory | Config / standing instruction | **Done** — SOUL policy on gateway; Telegram used `mcp__hermes_api__remember` without being told MCP |
| 2 | Grok handoff loop | Grok channel + turn `HERMES_GROK_HANDOFF` ask → on | **Done** — prod + BDK team `60586919`; result key `grok-result-<handoffId>` via MCP `remember` (soft-safe) |
| 3 | Jev soft on the API | Env / ops | **Done** — prod health shows `soft` + configured on `v0.3.10`; soft MCP memory bypass shipped; rollback is `shadow` + redeploy |
| 4 | Frontier comparison, then smaller model | Recorded eval + router | **Done** — comparison recorded; soft switch when `HERMES_MODEL_SMALL` set (optional) |
| 5 | Gateway skill-line hook | Control-plane | **Done** — MCP `suggest_skill` + production `SOUL.md` policy; Nous gateway LLM unchanged |

### Step 3 confirm (Jev soft)

Verified on `5011-Hermes` with Hermes image `v0.3.10` (2026-10-21):

```json
"jev":{"configured":true,"mode":"soft","model":"jev-1.13.0"}
```

| Check | Expect |
| --- | --- |
| `HERMES_JEV_MODE` in `.env.prod` | `soft` |
| `HERMES_JEV_API_KEY` | Set (length ≥ 16); never in health |
| `HERMES_JEV_MODEL` | Pinned id (prod uses `jev-1.13.0`) |
| Behaviour | Soft packs may change routing / withhold / filter; irreversible tools still ask a person |
| Soft MCP memory | MCP `list_skills` / `recall` / `remember` skip soft tool-call; soft memory-write still skips chatter |
| Soft handoff writeback | Grok channel MCP `remember` → `grok-result-<id>` recallable under soft |

Re-check anytime: `curl -sS http://127.0.0.1:8569/health` and read `jev`. Rollback: set `HERMES_JEV_MODE=shadow`, `unset IMAGE_TAG`, `deploy.sh prod`. See [jev-system-one.md](../../architecture/jev-system-one.md).

## Non-goals for this roadmap

- Merging gateway volume disks with API memory volumes
- Replacing the Nous gateway LLM with Jev
- Putting Grok alias tokens in `docker/env/.env.prod`

## Pointers

- Step 1 design: [2026-10-21-telegram-shared-memory-policy-design.md](2026-10-21-telegram-shared-memory-policy-design.md)
- Step 1 plan: [../plans/2026-10-21-telegram-shared-memory-policy.md](../plans/2026-10-21-telegram-shared-memory-policy.md)
- Step 2 plan: [../plans/2026-10-21-grok-handoff-loop.md](../plans/2026-10-21-grok-handoff-loop.md)
- Step 4 design: [2026-10-21-frontier-router-comparison-design.md](2026-10-21-frontier-router-comparison-design.md)
- Step 4 plan: [../plans/2026-10-21-frontier-router-comparison.md](../plans/2026-10-21-frontier-router-comparison.md)
- Step 5 design: [2026-10-21-gateway-skill-line-design.md](2026-10-21-gateway-skill-line-design.md)
- Step 5 plan: [../plans/2026-10-21-gateway-skill-line.md](../plans/2026-10-21-gateway-skill-line.md)
- Gateway skill-line SOUL policy: [../../architecture/gateway-skill-line-policy.md](../../architecture/gateway-skill-line-policy.md)
- Canonical policy text (copy-paste): [../../architecture/shared-memory-policy.md](../../architecture/shared-memory-policy.md)
- Grok architecture: [../../architecture/grok-hermes.md](../../architecture/grok-hermes.md)
- Soft MCP memory design: [2026-10-21-mcp-soft-memory-design.md](2026-10-21-mcp-soft-memory-design.md)
- Soft MCP memory plan: [../plans/2026-10-21-mcp-soft-memory.md](../plans/2026-10-21-mcp-soft-memory.md)
- Jev System One: [../../architecture/jev-system-one.md](../../architecture/jev-system-one.md)
