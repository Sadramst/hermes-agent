# Changelog

## [0.5.0] - 2026-11-16

### Added

- Authoritative root [AGENTS.md](../AGENTS.md) builder and runner agent manual covering local dev, Docker stacks, Ubuntu 24.04+ deployment, Telegram bot & cron setup, provider/OAuth routing, IDE MCP wiring, and troubleshooting.
- Version-controlled personal assistant gateway templates in `gateway/` (`SOUL.md`, `USER.md`, `config.yaml.example`, `cron.yaml.example`) and `docker/scripts/bootstrap-gateway.sh` to sync them cleanly into `/opt/data` with backups.
- Generic personal profile loading (`src/agent/profile.py`) and timezone utilities (`src/utils/time.py`) injecting `SOUL.md`, `USER.md`, and `HERMES_TIMEZONE` clock context into `HermesAgent.run_agent()`.
- `list_memories`, `current_time`, `GET /memories`, `GET /providers` (including official Gemini subscription readiness metadata), and CLI subcommands `memories`, `remember`, `recall`, `providers`.

### Simplified

- Consolidated documentation into `AGENTS.md`, `README.md`, `docs/DEPLOYMENT.md`, and `docs/CHANGELOG.md`, and streamlined `storage/skills/` into 5 generic everyday skills (`autonomous-problem-solver`, `bootstrap-hermes-stack`, `personal-development-coach`, `personal-financial-advisor`, `software-engineering-architect`).
- Removed legacy Jev (`src/agent/decisions/`, `src/services/jev.py`), Grok BDK handoff (`src/services/grok.py`, `.env.agent.example`), duplicate `ci-cd/` configs, contributor templates, and historical planning logs.
- Made Python source, environment templates, gateway persona/config examples, and skills generic and reusable for everyday personal use while keeping user-specific details cleanly in `gateway/USER.md`.

## [0.4.0] - 2026-10-26

### Added

- Autonomous multi-step tool loop (`POST /agent/run`, `POST /completions` `autonomous: true`, `hermes run`), Windows local launcher (`scripts/start-local.ps1`), and `autonomous-problem-solver` skill.
- Chunked document ingestion (`POST /documents`), hybrid vector + keyword RRF search (`GET /documents/search`), `HERMES_RAG_MODE` context injection, and `HERMES_MEMORY_INDEX` (`GET /memory/search`, `hermes reindex-memory`, `hermes migrate-documents`).
- Streamable HTTP MCP endpoint (`/mcp`), Chroma bearer-token gate (`chroma-gate`), and `hermes-gateway` dashboard Compose service.
