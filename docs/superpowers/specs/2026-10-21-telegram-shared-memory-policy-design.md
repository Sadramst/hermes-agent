# Design: Telegram prefers shared API memory

**Date:** 2026-10-21  
**Status:** approved for planning (user directed: do step 1 first; config only)  
**Roadmap:** [2026-10-21-shared-knowledge-roadmap.md](2026-10-21-shared-knowledge-roadmap.md)

## Problem

Telegram on `hermes-gateway` can call the shared API through MCP server `hermes-api`, and that path works. The gateway also has its own memory tools. After a successful shared write, Telegram explained that the two stores are separate. Operators and the model can still pick the wrong store for lasting facts.

## Goal

When a Telegram (or dashboard) user asks to remember or recall a fact that should be shared with Grok, the gateway uses `hermes-api` `remember` / `recall` / `search_documents` by default, not the local gateway memory tools.

## Non-goals

- Changing Python API code, MCP tool list, or Jev
- Disabling or deleting gateway `MEMORY.md` / built-in memory (still useful for persona)
- Syncing or migrating existing gateway memory files into the API
- Building the Grok handoff loop (roadmap item 2)

## Approaches considered

| Approach | Pros | Cons |
| --- | --- | --- |
| **A. Append policy to gateway `SOUL.md`** | Always on for Telegram; no project cwd needed; config only | Nous docs prefer SOUL for personality; this adds a short ops section |
| B. Gateway skill only | Fits “tool preference” conceptually | Skills are advisory; easy to ignore unless always selected |
| C. Repo-only docs, no live edit | Safe in git | Does not change Telegram behaviour until someone pastes |

**Choice: A**, with the canonical text tracked in this repository at [shared-memory-policy.md](../../architecture/shared-memory-policy.md). Operators copy that block into `/opt/data/SOUL.md` (or append after the existing identity). Optional later: also install a gateway skill that restates the same rules.

## Architecture

```text
Telegram / dashboard chat
        │
        ▼
hermes-gateway (SOUL.md includes Shared knowledge policy)
        │  prefers MCP hermes-api tools for lasting facts
        ▼
hermes-agent /mcp  →  memory files + Chroma + Jev
        ▲
Grok / Cursor MCP clients
```

No new containers. No compose changes. The MCP row `hermes-api` at `http://hermes-agent:8080/mcp/` stays as already tested.

## Components

1. **Canonical policy** in git: `docs/architecture/shared-memory-policy.md`
2. **Live identity** on the gateway volume: `/opt/data/SOUL.md` (append the Shared knowledge sections; keep existing personality text)
3. **Verification** via Telegram and Grok using a new key, without telling Telegram which tool to use

## Data flow

- Save path: user asks to remember → model calls `hermes-api` `remember` → API stores key → Grok `recall` returns the same value
- Read path: user asks what was stored → model calls `hermes-api` `recall` → same API file
- Local path: user asks for a persona-only note → model may use gateway memory; that value must not be required for Grok

## Error handling

- If `hermes-api` is disabled or Test fails, do not claim the fact is shared; fix MCP first
- If SOUL is truncated by gateway limits, keep the Shared knowledge section short (canonical file is already short)
- Do not put bearer tokens in SOUL.md

## Testing

1. Append policy; restart gateway (or start a new chat session if the dashboard reloads SOUL without restart)
2. Telegram: “Remember that the office wifi password hint is blue-orchid-7 under key office-wifi-hint.” Do **not** name the MCP tool.
3. Confirm Telegram’s confirmation mentions `hermes-api` / MCP remember (or equivalent), not only the built-in memory tool
4. Grok: recall `office-wifi-hint` → value matches
5. Optional negative check: ask Telegram to “note for yourself only that I prefer short replies” and confirm it does **not** create a shared API key unless asked to share

## Success criteria

- Unprompted tool choice for a shared fact uses `hermes-api`
- Grok can read that fact without Telegram naming the tool
- Canonical policy text lives in this repo for reinstall after volume wipe
