---
name: telegram-assistant-ops
version: 1.0.0
---
# Purpose

Operate Sadra's Telegram personal assistant gateway (`hermes-gateway`), DM topic routing, scheduled briefings, and bidirectional MCP sync across Telegram, Antigravity, Cursor, and the Dashboard.

# Inputs

- Telegram setup, DM topic organization, cron briefing design, or cross-channel memory question
- Gateway templates (`gateway/SOUL.md`, `gateway/USER.md`, `gateway/config.yaml.example`, `gateway/cron.yaml.example`)

# Outputs

- Verified Telegram bot configuration steps (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`), DM topic layout, or cron schedule
- Cross-channel facts synced to `hermes-api` MCP (`remember`, `recall`, `list_memories`, `save_document`, `search_documents`)

# Execution flow

1. Verify `hermes-gateway` uses `docker/env/.env.gateway` (or `/opt/data/.env` via `hermes gateway setup`) without empty-string overrides hiding saved tokens.
2. Confirm `mcp_servers.hermes-api` points to internal Docker URL `http://hermes-agent:8080/mcp/` with `Authorization: "Bearer ${HERMES_API_TOKEN}"`.
3. Route lasting facts from Telegram into `hermes-api` (`remember` / `save_document`) so Antigravity, Cursor, and CLI sessions share one memory store.
4. Keep Telegram responses concise, scannable, and mobile-friendly, using DM topics (`General`, `Engineering & Ops`, `Personal Growth`, `Finance Advisory`, `Briefings & Alerts`) when Threaded Mode is active.

# Error handling

- If `hermes-api` fails inside `hermes-gateway`, verify `HERMES_MCP_ENABLED=on` and `hermes-agent` is in `HERMES_MCP_ALLOWED_HOSTS` via `hermes mcp test hermes-api`.

# Logging

Gateway Telegram events log inside `hermes-gateway`; shared MCP calls log on `hermes-agent` (`hermes`).

# Versioning

Bump when Telegram gateway environment variables, topic structures, or MCP tool contracts change.

# Test coverage

- `tests/unit/test_mcp.py`
- `tests/e2e/test_stack_contract.py`

# Documentation references

- `docs/architecture/telegram-gateway.md`
- `docs/architecture/personal-assistant.md`
- `gateway/SOUL.md`

