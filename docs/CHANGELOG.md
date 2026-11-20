# Changelog

## [0.6.0] - 2026-11-20

### Added

- **Always-On Mini PC Home Brain & Multi-Project Commander Stack:**
  - Sandboxed `WorkspaceManager` (`src/services/workspace.py`) gated by `HERMES_WORKSPACE_MODE` (`off`/`ro`/`rw`), `HERMES_PROJECTS_DIR`, and `HERMES_WORKSPACE_ALLOWED_CMDS` with strict path-jail protection, symlink/traversal guards, secret file denylist (`.git/**`, `.env` except `*.example`/`*.sample`, keys/certs, `auth.json`), non-shell allowlisted execution, and `ask_person` / HTTP `409` confirmation gating on destructive commands (`rm`, `git push --force`, `git reset --hard`, `git clean -f`).
  - Brain directory ingestion service (`src/services/ingest.py`) for chunking & indexing Markdown/text/code files under `/knowledge` and `/workspace` with SHA-256 deduplication and collision-free document IDs.
  - Protected HTTP routes (`GET /projects`, `GET /projects/{p}/files`, `GET /projects/{p}/read`, `GET /projects/{p}/search`, `POST /projects/{p}/write`, `POST /projects/{p}/exec`, `POST /projects/{p}/ingest`), 6 workspace agent tools in `run_agent()`, workspace telemetry in `/health`, and CLI subcommands (`hermes projects`, `hermes ingest`).
  - Mini PC Docker Compose overlay (`docker/docker-compose.minipc.yml`) mounting host `/workspace` and `/knowledge` across both `hermes-agent` and `hermes-gateway`, plus optional `cloudflared` tunnel profile (`CLOUDFLARE_TUNNEL_TOKEN`), `docker/env/.env.minipc.example`, `docker/scripts/setup-minipc.sh`, `docker/scripts/sync-brain.sh`, and `docker/scripts/backup-brain.sh`.
  - Complete Mini PC & Remote Access Architecture blueprint ([MINIPC_ARCHITECTURE.md](MINIPC_ARCHITECTURE.md)), plus updated `AGENTS.md`, `DEPLOYMENT.md`, `gateway/` templates, and QA unit/contract tests (`test_workspace.py`, `test_ingest.py`).
- Added `git` to the runtime container image and included `AGENTS.md` in the Docker `test` stage in `docker/Dockerfile`.

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
