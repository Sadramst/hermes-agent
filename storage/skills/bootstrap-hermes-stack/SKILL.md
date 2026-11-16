---
name: bootstrap-hermes-stack
version: 1.19.0
---
# Purpose

Bring up the Hermes Agent service with ChromaDB, persistent memory and skills, Telegram gateway, and provider routing for `dev`, `test`, or `prod`.

# Inputs

- Environment (`dev`, `test`, or `prod`), `docker/env/.env.<env>`, `docker/env/.env.gateway`, and `gateway/` templates
- Provider configuration (`HERMES_PROVIDER_AUTH_MODE`, OpenRouter / Google AI Studio / NVIDIA / Claude & ChatGPT OAuth)

# Outputs

- Healthy containers (`GET /health`, `GET /providers`) on `hermes-<env>-net`
- `hermes-gateway` Telegram bot + Dashboard (`:9119`) synced via `bootstrap-gateway.sh` and verified on 9-tool `/mcp`

# Execution flow

1. Follow `AGENTS.md` (mandatory builder/runner guide) or `docs/DEPLOYMENT.md`.
2. Deploy with `bash docker/scripts/deploy.sh <dev|test|prod>`. In `prod`, run `bash docker/scripts/bootstrap-gateway.sh` to sync `SOUL.md`, `USER.md`, and `config.yaml`.
3. Route models cleanly: API keys (`OpenRouter` / `Google AI Studio`) today on both API & gateway, free `NVIDIA NIM` compression/fallback, optional `Claude`/`ChatGPT` OAuth or `Nous Portal` in `hermes-gateway`, and respect official pending Gemini subscription status (`not live yet, no date`).
4. Verify `/health` (`chroma.reachable: true`, `assistant.profile_loaded: true`) and `hermes mcp test hermes-api` (9 tools).

# Error handling

- Missing prod secrets (`CHROMA_AUTH_TOKEN`, `HERMES_API_TOKEN`, `HERMES_MODEL_*`) fail closed at startup.
- Invalid bearer tokens return `401`; unlisted MCP `Host` headers return `421`.

# Logging

Logs under `hermes` (`timestamp level [hermes] message env=<HERMES_ENV>`) without logging keys, OAuth tokens, or prompts.

# Versioning

Skill version `1.19.0` tracks container bootstrap, Telegram gateway, and provider routing contracts.

# Test coverage

- `tests/unit/test_skills.py`
- `tests/unit/test_health.py`
- `tests/e2e/test_stack_contract.py`

# Documentation references

- `AGENTS.md`
- `docs/DEPLOYMENT.md`
- `README.md`
