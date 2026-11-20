---
name: bootstrap-hermes-stack
version: 1.19.0
---
# Purpose

Bring up the Hermes Agent service with ChromaDB, persistent memory and skills, Telegram gateway, Mini PC workspace brain, and provider routing for `dev`, `test`, `prod`, or `minipc`.

# Inputs

- Environment (`dev`, `test`, `prod`, or `minipc`), `docker/env/.env.<env>`, `docker/env/.env.gateway`, `docker/env/.env.minipc`, and `gateway/` templates
- Provider configuration (`HERMES_PROVIDER_AUTH_MODE`, OpenRouter / Google AI Studio / NVIDIA / Claude & ChatGPT OAuth)

# Outputs

- Healthy containers (`GET /health`, `GET /providers`, `GET /projects`) on `hermes-<env>-net`
- `hermes-gateway` Telegram bot + Dashboard (`:9119`) synced via `bootstrap-gateway.sh`, mounted `/workspace` + `/knowledge`, and verified on 9-tool `/mcp`

# Execution flow

1. Follow `AGENTS.md` (mandatory builder/runner guide), `docs/MINIPC_ARCHITECTURE.md`, or `docs/DEPLOYMENT.md`.
2. Deploy with `bash docker/scripts/deploy.sh <dev|test|prod|minipc>` (or `bash docker/scripts/setup-minipc.sh` on a fresh Mini PC), then run `bash docker/scripts/bootstrap-gateway.sh`.
3. Route models cleanly: API keys (`OpenRouter` / `Google AI Studio`) today on both API & gateway, free `NVIDIA NIM` compression/fallback, optional `Claude`/`ChatGPT` OAuth or `Nous Portal` in `hermes-gateway`, and respect official pending Gemini subscription status (`not live yet, no date`).
4. Sync `/knowledge` + projects via `bash docker/scripts/sync-brain.sh --projects` and back up volumes via `bash docker/scripts/backup-brain.sh`.
5. Verify `/health` (`chroma.reachable: true`, `assistant.profile_loaded: true`, `workspace.enabled`) and `hermes mcp test hermes-api` (9 tools).

# Error handling

- Missing prod secrets (`CHROMA_AUTH_TOKEN`, `HERMES_API_TOKEN`, `HERMES_MODEL_*`) fail closed at startup.
- Invalid bearer tokens return `401`; unlisted MCP `Host` headers return `421`; secret files and destructive workspace commands fail closed (`403`/`409`/`ask_person`).

# Logging

Logs under `hermes` (`timestamp level [hermes] message env=<HERMES_ENV>`) without logging keys, OAuth tokens, or prompts.

# Versioning

Skill version `1.19.0` tracks container bootstrap, Mini PC Brain deployment, Telegram gateway, and provider routing contracts.

# Test coverage

- `tests/unit/test_skills.py`
- `tests/unit/test_health.py`
- `tests/unit/test_workspace.py`
- `tests/e2e/test_stack_contract.py`

# Documentation references

- `AGENTS.md`
- `docs/MINIPC_ARCHITECTURE.md`
- `docs/DEPLOYMENT.md`
- `README.md`
