# MCP soft memory (tool-call bypass)

**Status:** approved design  
**Date:** 2026-10-21  
**Parent:** [jev-system-one.md](../../architecture/jev-system-one.md) (tool-call pack soft hold; memory-write soft chatter skip); [shared-memory-policy.md](../../architecture/shared-memory-policy.md)

## Goal

Under `HERMES_JEV_MODE=soft`, MCP clients (including Grok via Cursor) must be able to run `list_skills`, `recall`, and `remember` without the soft **tool-call** pack refusing the call when Jev’s choice does not match the tool name. Soft **memory-write** still skips one-shot chatter. HTTP `POST /tools` keeps soft tool-call enforcement as today.

## Non-goals

- Bypassing soft tool-call for HTTP `/tools` or for other MCP tools (`search_documents`, `complete`, `suggest_skill` already skip `run_tools`)
- Always-persisting MCP `remember` (no shadow-like “always store” for MCP)
- Key-prefix allowlists, new env flags, or new Jev packs
- Changing soft supervisor / loop behavior for batches that still use `run_tools`

## Approach

**Direct agent methods from MCP for the memory trio** — same pattern as `search_documents` / `complete` / `suggest_skill`.

Today `mcp_tools.call_tool` routes `list_skills`, `recall`, and `remember` through `agent.run_tools`, which under soft applies `hold_for` (refuse when `name != choice`). Change those three to call `HermesAgent.list_skills`, `recall`, and `remember` directly and map outputs to the same strings the tool runner already returns. Soft memory-write stays inside `remember`.

## Behavior matrix

| Caller | Soft tool-call | Soft memory-write |
| --- | --- | --- |
| MCP `list_skills`, `recall`, `remember` | bypass (no `run_tools`) | N/A; `remember` still gated |
| MCP `search_documents`, `complete`, `suggest_skill` | already bypass | N/A |
| HTTP `/tools` (allowlisted tools) | enforce (`hold_for`) | enforce on `remember` |

### MCP output mapping

Reuse the existing tool-layer strings so clients see no contract change:

| Tool | Success / notes |
| --- | --- |
| `list_skills` | Same multiline `name version` text as `_skills` in `tools.py` (or empty-skills message) |
| `recall` | Value string, or the existing missing-key text on `FileNotFoundError` |
| `remember` | `"stored"` if `agent.remember` returns true; `"skipped"` if soft memory-write drops chatter |

Argument validation stays in `call_tool` (exact key sets, string values). Unknown MCP names still return the existing refused text.

## Change surface

1. **`src/api/mcp_tools.py`** — For `list_skills` / `recall` / `remember`, invoke agent methods and map outputs; do not call `run_tools`.
2. **Tests** — Soft mode: MCP trio still succeeds when a mocked tool-call judgment would refuse; chatter `remember` still returns `skipped`; at least one soft `/tools` case still refuses a mismatched hold.
3. **Docs** — One short note in [shared-memory-policy.md](../../architecture/shared-memory-policy.md): MCP `list_skills` / `recall` / `remember` skip soft tool-call but not soft memory-write.

## Data flow

```text
MCP client → /mcp remember(key, value)
  → call_tool → agent.remember(key, value)
       → memory-write pack (soft may skip chatter)
       → "stored" | "skipped"
```

HTTP `/tools` with `{calls:[{name:"remember",...}]}` still goes through `run_tools` → soft tool-call → (if run) `remember` → soft memory-write.

## Success criteria

- Soft e2e: MCP `remember` of a durable note returns `stored` (or clear `skipped` only when chatter); MCP `recall` of that key returns the value.
- Soft HTTP `/tools` still holds/refuses when soft tool-call would refuse today.
- No new configuration knobs.

## Out of scope for follow-ups

Broader “trusted MCP” policy, always-store prefixes, or aligning HTTP `/tools` with this bypass.
