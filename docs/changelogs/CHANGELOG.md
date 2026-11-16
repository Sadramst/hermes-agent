# Changelog

## [0.5.0] - 2026-11-16

### Added

- Version-controlled personal assistant gateway templates under `gateway/` (`SOUL.md`, `USER.md`, `config.yaml.example`, `cron.yaml.example`) and `docker/scripts/bootstrap-gateway.sh` to sync them into `hermes-gateway` `/opt/data` with automatic backups.
- Personal assistant profile loading (`src/agent/profile.py`) and timezone clock reporting (`src/utils/time.py`) injecting Sadra's `SOUL.md` / `USER.md` context and `HERMES_TIMEZONE` into `HermesAgent.run_agent()` (`POST /agent/run`, `POST /completions` with `autonomous=true`, `hermes run`).
- `list_memories`, `current_time`, `GET /memories`, `GET /providers`, and CLI subcommands `memories`, `remember`, `recall`, `providers`.
- Personal assistant skills (`software-engineering-architect`, `personal-development-coach`, `personal-financial-advisor`, `telegram-assistant-ops`, `provider-and-subscription-routing`) plus `autonomous-problem-solver` v1.1.0.
- Concise, personalized documentation: [personal-assistant.md](../architecture/personal-assistant.md), [telegram-gateway.md](../architecture/telegram-gateway.md), [providers-and-subscriptions.md](../architecture/providers-and-subscriptions.md), and streamlined [ubuntu-server.md](../deployment/ubuntu-server.md).
- Telegram gateway env template (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, optional `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) in `docker/env/.env.gateway.example` without empty-string Compose overrides.

### Changed & Simplified

- Removed legacy TypeSafe Jev (`src/agent/decisions/`, `src/services/jev.py`), Grok BDK handoff (`src/services/grok.py`, `.env.agent.example`), duplicate `ci-cd/` configs, contributor templates, and `docs/superpowers/` + `docs/architecture/history/` bloat so the codebase focuses purely on Sadra's personal assistant stack.
- `/mcp` exposes 9 shared tools (`complete`, `current_time`, `list_memories`, `list_skills`, `recall`, `remember`, `save_document`, `search_documents`, `search_memory`) while keeping `delete_memory` strictly off `/mcp`.
- `GET /health` reports secret-free `provider` (`auth_mode`, `gemini_subscription`) and `assistant` (`timezone`, `profile_loaded`) fields.
- Unified all configurations and domains onto `sadramst.dev` and `Sadramst/hermes-agent`.

## [0.4.0] - 2026-10-26

### Added

- Autonomous multi-step tool loop (`POST /agent/run`, `POST /completions` `autonomous: true`, `hermes run`), Windows local launcher (`scripts/start-local.ps1`), and `autonomous-problem-solver` skill.
- Chunked document ingestion (`POST /documents`), hybrid vector + keyword RRF search (`GET /documents/search`), `HERMES_RAG_MODE` context injection, and `HERMES_MEMORY_INDEX` (`GET /memory/search`, `hermes reindex-memory`, `hermes migrate-documents`).
- Streamable HTTP MCP endpoint (`/mcp`), Chroma bearer-token gate (`chroma-gate`), and `hermes-gateway` dashboard Compose service.
