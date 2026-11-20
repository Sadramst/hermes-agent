# Hermes Agent

> **Builder & Runner Agents:** Read [AGENTS.md](AGENTS.md) first before modifying code, running services locally, configuring Telegram/OAuth providers, or deploying on your Mini PC or Ubuntu Server.

**Hermes Agent** is a lean, self-hosted **Personal Assistant Operating System & Always-On Brain** for everyday work, multi-project engineering, daily productivity and habits, non-custodial personal finance tracking, and cross-device knowledge recall.

It connects two Docker Compose services over Model Context Protocol (`/mcp/`) with a shared `/workspace` project root and `/knowledge` Brain vault:
1. **`hermes-agent` (this Python repository — `FastAPI` + `MCP` + `ChromaDB` + `WorkspaceManager`)**: persistent dotted-namespace memory (`profile.*`, `work.*`, `dev.*`, `goal.*`, `habit.*`, `study.*`, `finance.*`, `ops.*`), semantic RAG (`hermes-documents-v2`) with directory ingestion (`hermes ingest`), sandboxed multi-project read/write/command control (`/projects/*`), 5 concise `SKILL.md` skills, and an autonomous multi-step loop (`POST /agent/run`).
2. **`hermes-gateway` (`nousresearch/hermes-agent:latest`)**: always-on **Telegram Bot**, **Web Dashboard** (`:9119`), scheduled cron briefings, `SOUL.md` / `USER.md` identity, and multi-provider OAuth/API routing synced with `hermes-agent`.

```mermaid
flowchart TB
  user["Personal User Anywhere\n(Telegram, Tailscale VPN / Cloudflare Tunnel, IDE MCP, CLI)"]
  subgraph net ["Docker network: hermes-net"]
    gateway["hermes-gateway\nTelegram + Dashboard :9119 + Cron\nSOUL.md + USER.md + /workspace + /knowledge"]
    agent["hermes-agent\nDev :8080 | Prod/MiniPC :8569\n/health /providers /memories /projects/* /agent/run /mcp"]
    gate["chroma-gate :8000"]
  end
  subgraph chromaNet ["Private chroma-net"]
    chroma["chromadb :8000"]
  end
  host["Host Persistence\nworkspace/ + knowledge/ + backups/"]

  user --> gateway
  user -->|"MCP / HTTP (Tailscale / HTTPS)"| agent
  gateway -->|"MCP http://hermes-agent:8080/mcp/"| agent
  agent --> gate --> chroma
  gateway --- host
  agent --- host
```

## Documentation

- **Builder & Runner Manual (complete end-to-end spec):** [AGENTS.md](AGENTS.md)
- **Mini PC Always-On Brain & Remote Architecture:** [docs/MINIPC_ARCHITECTURE.md](docs/MINIPC_ARCHITECTURE.md)
- **Ubuntu Server 24.04+, Mini PC, Telegram & Provider Guide:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- **Changelog:** [docs/CHANGELOG.md](docs/CHANGELOG.md)
- **ChromaDB service notes:** [vector-db/chromadb/README.md](vector-db/chromadb/README.md)

## Quick Start

### 1. Personalize & Run Locally (Windows / Linux)

Edit [gateway/USER.md](gateway/USER.md) and copy `.env.example` → `.env.local` (add your OpenRouter or Google AI Studio API key and local `HERMES_TIMEZONE`):

```powershell
# Windows (.venv)
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\pytest -q -m "not integration"

Copy-Item .env.example .env.local
.\scripts\start-local.ps1
```

### 2. Always-On Mini PC Home Brain (`minipc`)

```bash
# First-time host setup (generates tokens, .env files, workspace/ + knowledge/ + ACLs)
bash docker/scripts/setup-minipc.sh --no-start
# Fill API/Telegram keys in .env.prod + .env.gateway and host paths in .env.minipc, then:
bash docker/scripts/deploy.sh minipc
bash docker/scripts/bootstrap-gateway.sh --force-config
bash docker/scripts/sync-brain.sh --projects
```

### 3. Docker Compose Stack (`dev`, `test`, `prod`, `minipc`)

```bash
# Development stack (agent :8080, chromadb :8000)
bash docker/scripts/deploy.sh dev

# Offline CI-style test suite inside Docker
bash docker/scripts/deploy.sh test

# Cloud VPS stack pulling prebuilt GHCR images
bash docker/scripts/deploy.sh prod
```

## Providers & Official Gemini Subscription Status

- **Live today on `hermes-agent` & `hermes-gateway`:** OpenRouter (`google/gemini-2.5-flash` / `~google/gemini-flash-latest`), Google AI Studio API (`GOOGLE_API_KEY` / `GEMINI_API_KEY`), NVIDIA NIM free fallback & compression (`nvidia/nemotron-3.5-super-vl-120b-a12b`), GitHub Copilot (`gpt-5.4`), plus **Claude Pro/Max OAuth**, **ChatGPT/Codex OAuth**, and **Nous Portal** inside `hermes-gateway` (`hermes model` / `hermes setup --portal`).
- **Gemini Subscriptions (official status):** Today Gemini in Hermes runs on an API key, not consumer Gemini plans. Nous Research is working with Google to bring Gemini subscriptions into Hermes the Google-approved way (**not live yet, no release date**). Inspect readiness anytime via `GET /providers`, `GET /health`, or `hermes providers`.

## Key Endpoints & CLI

- **HTTP / MCP:** `GET /health`, `GET /providers`, `GET /memories`, `GET /memory/search`, `GET /projects`, `GET /projects/{project}/files`, `GET /projects/{project}/read`, `GET /projects/{project}/search`, `POST /projects/{project}/write`, `POST /projects/{project}/exec`, `POST /projects/{project}/ingest`, `POST /documents`, `GET /documents/search`, `POST /completions`, `POST /agent/run`, `POST /tools`, and `/mcp` (9 shared tools; `delete_memory` and destructive commands require human confirmation).
- **CLI:** `hermes health`, `hermes providers`, `hermes skills`, `hermes memories`, `hermes remember`, `hermes recall`, `hermes projects`, `hermes ingest`, `hermes run "..."`, `hermes migrate-documents`, `hermes reindex-memory`.

## Repository Layout

- [AGENTS.md](AGENTS.md) — Authoritative builder/runner setup, Mini PC, deploy, Telegram, provider & verification handbook
- `gateway/` — Everyday personal templates (`SOUL.md`, `USER.md`, `config.yaml.example`, `cron.yaml.example`)
- `src/` — Agent loop, generic profile loader, timezone utilities, FastAPI + MCP server, sandboxed workspace manager, Brain ingestion, memory, RAG, CLI
- `storage/skills/` — 5 concise everyday skills (`autonomous-problem-solver`, `bootstrap-hermes-stack`, `personal-development-coach`, `personal-financial-advisor`, `software-engineering-architect`)
- `docker/` — `Dockerfile`, `docker-compose.{dev,test,prod,minipc}.yml`, env templates, deploy, Mini PC setup, brain sync & backup scripts
- `scripts/` — Windows local launcher (`start-local.ps1`) and retrieval evaluator (`eval_retrieval.py`)
- `docs/` — Mini PC architecture ([MINIPC_ARCHITECTURE.md](docs/MINIPC_ARCHITECTURE.md)), deployment guide ([DEPLOYMENT.md](docs/DEPLOYMENT.md)), & changelog ([CHANGELOG.md](docs/CHANGELOG.md))
