# Shared memory policy (gateway standing instruction)

Paste the block below into the Hermes gateway identity file so Telegram (and dashboard chat) prefer the Python API for facts that must reach Grok or Cursor.

**Where it lives on the server:** the gateway volume file `SOUL.md` under Hermes home (production Docker: inside `hermes-prod-gateway` at `/opt/data/SOUL.md`). SOUL is always injected for messaging sessions. Project `AGENTS.md` is not reliable for Telegram because those sessions often have no project cwd.

**Do not** put secrets, tokens, or host IPs in this policy. Tool names may use the MCP server name `hermes-api`.

---

## Shared knowledge (API)

Facts that must be visible to Grok, Cursor, Telegram, and any other MCP client belong in the Hermes API key-value store and document search.

- To save a lasting fact: call the MCP tools on server `hermes-api` — `remember` with a short stable key and the value.
- To read a lasting fact: call `hermes-api` `recall` with that key.
- To search saved documents: call `hermes-api` `search_documents`.
- Prefer those tools whenever the user asks to remember, recall, or share knowledge across channels.

## Soft mode (Jev)

When `HERMES_JEV_MODE=soft`, MCP `list_skills`, `recall`, and `remember` skip the soft **tool-call** hold so trusted MCP clients can use shared memory. Soft **memory-write** still applies: one-shot chatter on `remember` returns `skipped` and is not stored. HTTP `POST /tools` still enforces soft tool-call.

## Local gateway memory

The built-in gateway memory tools and `MEMORY.md` / `USER.md` stay on this gateway only. Use them for persona notes and session preferences that must not leave this gateway. Do not use them for facts that should be shared with Grok or Cursor.

## When unsure

If a fact should still be true tomorrow for both Telegram and Grok, use `hermes-api` `remember`. Say which tool you used when you confirm the save.
