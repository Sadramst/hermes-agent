---
name: provider-and-subscription-routing
version: 1.0.0
---
# Purpose

Configure and route Hermes across OpenRouter, Google AI Studio API keys, NVIDIA NIM, GitHub Copilot, Claude/ChatGPT OAuth, Nous Portal, and the upcoming official Gemini Subscription OAuth.

# Inputs

- Provider selection, fallback routing, subscription OAuth question, or model cost optimization request
- Active settings (`providers` endpoint/CLI, `gateway/config.yaml.example`, `docker/env/.env.gateway.example`)

# Outputs

- Recommended provider/fallback configuration (`config.yaml`, `.env.prod`, `.env.gateway`) matching Sadra's active keys or OAuth plans
- Accurate status on official Gemini Subscription OAuth readiness without unofficial workarounds

# Execution flow

1. Check current API provider readiness (`GET /providers` or `hermes providers`) and gateway provider slots.
2. Route everyday `hermes-agent` API turns through OpenRouter (`google/gemini-2.5-flash` / `google/gemini-2.5-flash-lite`) or Google AI Studio's OpenAI-compatible endpoint (`GOOGLE_API_KEY` / `GEMINI_API_KEY`).
3. On `hermes-gateway`, configure everyday chat on OpenRouter (`~google/gemini-flash-latest`), free fallback + compression on NVIDIA NIM (`nvidia/nemotron-3.5-super-vl-120b-a12b`), direct fallback on Google AI Studio (`gemini-2.5-flash`), and optional Claude Pro/Max OAuth, ChatGPT/Codex OAuth, Nous Portal (`hermes setup --portal`), or GitHub Copilot (`gpt-5.4`) for hard turns.
4. Enforce the Gemini subscription rule: today Gemini runs on an API key because Nous Research and Google are still finalizing official Google-approved Gemini Subscription OAuth (not live yet, no date). Reject unapproved third-party Gemini plan plugins/scrapers.

# Error handling

- If a provider returns 401/403/410 (e.g. retired NVIDIA embedding model or classic `ghp_` Copilot token), switch to the verified OpenRouter or direct API key path documented in `docs/architecture/providers-and-subscriptions.md`.

# Logging

`hermes providers` and `GET /health` report `provider.auth_mode` and `gemini_subscription` status while omitting all API keys and OAuth tokens.

# Versioning

Bump when Nous Research ships official Google-approved Gemini Subscription OAuth or updates default model routing.

# Test coverage

- `tests/unit/test_personal_assistant.py`
- `tests/unit/test_config.py`

# Documentation references

- `docs/architecture/providers-and-subscriptions.md`
- `gateway/config.yaml.example`
- `README.md`

