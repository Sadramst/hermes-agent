# AGENTS.md — Hermes Agent Builder & Runner Manual

> **MANDATORY FIRST READ:** Any builder, coding, deployment, or runner agent entering this repository **must read this file completely before modifying code, starting services, or deploying**. This document is the single source of truth to build, customize, test, run locally, deploy to an always-on **Mini PC Home Brain** or **Ubuntu Server 24.04+**, configure Telegram, configure AI providers/OAuth subscriptions, control multi-project workspaces remotely, ingest knowledge vaults, connect IDE MCP from outside the house, and troubleshoot the entire stack without guesswork.

---

## 1. Purpose & Architecture Overview

**Hermes Agent** is a lean, self-hosted **Personal Assistant Operating System & Always-On Brain** built for everyday personal and professional use across:
- **Multi-Project Work & Software Engineering** (inspecting, searching, editing, testing, and managing repositories mounted under `/workspace`)
- **Personal Knowledge Brain (`knowledge/` + ChromaDB RAG)** (Markdown notes, Obsidian vaults, docs, runbooks ingested with SHA-256 deduplication and `[label]` citations)
- **Daily Productivity, Learning & Habits** (morning priorities, goal tracking, study synthesis, weekly reviews)
- **Personal Financial Advisory & Planning** (budgeting, cashflow runway, scenario modeling — **strictly analytical & non-custodial**)
- **Life Admin & Knowledge Management** (drafting messages, travel/errands, persistent cross-device notes)

It runs two coordinated services plus ChromaDB:
1. **`hermes-agent` (this Python repository — FastAPI + MCP + ChromaDB RAG + Workspace Commander + CLI):**
   - Persistent file-backed dotted memory (`profile.*`, `work.*`, `dev.*`, `goal.*`, `habit.*`, `study.*`, `finance.*`, `ops.*`)
   - Chunked semantic document store (`POST /documents`, `GET /documents/search`, hybrid vector + keyword RRF) + directory ingestion (`hermes ingest`, `POST /projects/{project}/ingest`)
   - Sandboxed multi-project controller (`WorkspaceManager`, `GET/POST /projects/*`, allowlisted non-shell execution, secret file denylist)
   - Concise `SKILL.md` skills (`storage/skills/*/SKILL.md`)
   - Autonomous multi-step tool loop (`POST /agent/run`, `hermes run`) that injects `gateway/SOUL.md`, `gateway/USER.md`, `HERMES_TIMEZONE` clock, and active workspace tools
   - Authenticated Streamable HTTP MCP endpoint (`/mcp`) exposing 9 shared tools
2. **`hermes-gateway` (`nousresearch/hermes-agent:latest`):**
   - Always-on **Telegram Bot** (outbound long-polling, optional DM Topics), **Web Dashboard** (`:9119`), scheduled **cron** briefings, and multi-provider **OAuth/API routing**, sharing `/workspace`, `/knowledge`, and MCP (`http://hermes-agent:8080/mcp/`) with `hermes-agent`.

```mermaid
flowchart TB
  user["User Outside Home\n(Telegram, Tailscale / Cloudflare HTTPS, Antigravity/Cursor MCP)"]
  subgraph net ["Docker network: hermes-<env>-net"]
    gw["hermes-gateway\nTelegram + Dashboard :9119 + Cron\n/opt/data + /workspace + /knowledge"]
    agent["hermes-agent\nDev :8080 | Prod/MiniPC :8569\n/health /providers /memories /projects/* /agent/run /mcp"]
    gate["chroma-gate :8000 (Prod/MiniPC)\nBearer token proxy"]
    cf["cloudflared (Optional --profile tunnel)\nZero-port public HTTPS"]
  end
  subgraph chromaNet ["Private network (Prod/MiniPC: hermes-prod-chroma-net)"]
    chroma["chromadb :8000\n/data persistence"]
  end
  host["Host Persistence\nworkspace/ + knowledge/ + backups/"]

  user -->|"Telegram Bot API (outbound poll)"| gw
  user -->|"Tailscale VPN or Cloudflare Tunnel"| gw
  user -->|"HTTP / Bearer MCP"| agent
  cf -.-> gw
  cf -.-> agent
  gw -->|"MCP http://hermes-agent:8080/mcp/"| agent
  agent --> gate --> chroma
  gw --- host
  agent --- host
```

---

## 2. Hard Invariants (Do Not Violate)

Any builder or runner agent modifying or operating this repo **must preserve these invariants**:

1. **Non-Custodial Financial Safety:** Never add autonomous trading, bank/exchange mutations, payments, or credential storage (no bank logins, card numbers, PINs, or wallet seed phrases in memory files, docs, or code).
2. **Approved Provider & Gemini Subscription Policy:**
   - Today, **Gemini in Hermes runs on an API key** (`OPENROUTER_API_KEY` or `GOOGLE_API_KEY` / `GEMINI_API_KEY`), **not** consumer Gemini plans.
   - **Claude Pro/Max** and **ChatGPT Plus/Pro** subscriptions work in `hermes-gateway` today via official OAuth (`hermes model`).
   - **Nous Research + Google** are actively working on official Google-approved Gemini subscription support (**not live yet, no release date**).
   - **NEVER** implement, bundle, or suggest unapproved consumer Gemini web scrapers, cookie hijackers, or unofficial OAuth proxy bypasses.
3. **Secret Isolation:**
   - Untracked secret and local data files (`.env.local`, `docker/env/.env.prod`, `docker/env/.env.gateway`, `docker/env/.env.minipc`, `workspace/`, `knowledge/`, `backups/`, `/opt/data/.env`, `/opt/data/auth.json`) must stay gitignored.
   - Never log, echo, or return `HERMES_API_TOKEN`, `CHROMA_AUTH_TOKEN`, `HERMES_MODEL_API_KEY`, `TELEGRAM_BOT_TOKEN`, or host workspace secrets in `/health`, `/providers`, `/projects`, or logs.
   - `WorkspaceManager` and `ingest_directory` must keep blocking `.git/**`, `.env` / `.env.*` (except `*.example` / `*.sample`), `auth.json`, `credentials.json`, SSH keys, and `.pem`/`.key`/`.p12`/`.pfx`/`.jks`/`.keystore`/`.kdbx`.
   - Keep `docker/docker-compose.prod.yml` free of empty `${TELEGRAM_BOT_TOKEN:-}` overrides on `hermes-gateway` so interactive `/opt/data/.env` setup stays intact.
4. **Container & MCP Security:**
   - Keep `cap_drop: [ALL]` on `hermes-agent`, non-root `USER hermes` (`uid=10001`) in `docker/Dockerfile`, and `chroma-gate` isolating `chromadb` in `prod`/`minipc`.
   - Keep destructive `delete_memory` off `/mcp` (9 MCP tools only: `complete`, `current_time`, `list_memories`, `list_skills`, `recall`, `remember`, `save_document`, `search_documents`, `search_memory`).
   - Direct `/tools`, `/agent/run`, and `/projects/{project}/exec` calls involving `delete_memory` or destructive commands (`rm`, `git push --force`, `git reset --hard`, `git clean -f`, etc.) must return `ask_person` (`409` on HTTP).
5. **Line Endings & Contracts:**
   - All `docker/scripts/*.sh` files **must keep LF (`\n`) endings** (`.gitattributes` enforces `*.sh text eol=lf`) and pass `bash -n`.
   - All edits must keep `pytest -q -m "not integration"` passing with zero failures.

---

## 3. Repository & Code Map

| Path | Role |
| --- | --- |
| `AGENTS.md` | **This file** — complete Builder & Runner Agent manual. |
| `README.md` | Human quickstart & project overview. |
| `docs/MINIPC_ARCHITECTURE.md` | Always-on Mini PC Brain topology, security boundaries, BIOS/OS setup & remote access guide. |
| `docs/DEPLOYMENT.md` | Ubuntu Server 24.04+ VPS, Mini PC Docker, Tailscale/Tunnel, Telegram & provider guide. |
| `docs/CHANGELOG.md` | Release history (`0.6.0`, `0.5.0`, `0.4.0`). |
| `gateway/SOUL.md` | Assistant persona, everyday domains, `/workspace` rules, non-custodial bounds, shared MCP rules. |
| `gateway/USER.md` | Personal user profile, Mini PC host context, style, and memory prefixes (**customize here**). |
| `gateway/config.yaml.example` | Default `hermes-gateway` model routing, fallbacks, Telegram DM topics, and MCP link. |
| `gateway/cron.yaml.example` | Everyday morning, evening, weekly review, and Mini PC maintenance prompt templates. |
| `src/agent/core.py` | `HermesAgent` orchestrator, completions, `/agent/run` loop, RAG, workspace & ingestion facade. |
| `src/agent/profile.py` | Generic loader injecting `SOUL.md`, `USER.md`, clock, and active workspace rules into `run_agent()`. |
| `src/agent/tools.py` | Allowlisted tools (`9` base + `delete_memory` confirm-gated + `6` mode-gated workspace tools). |
| `src/agent/prompt.py` | Skill-index + optional RAG `## Context` assembly for `/completions`. |
| `src/api/app.py` | FastAPI factory (`/health`, `/providers`, `/memories`, `/projects/*`, `/documents`, `/completions`, `/agent/run`, `/tools`, `/mcp`). |
| `src/api/mcp_tools.py` | 9 shared MCP tools (`delete_memory` excluded). |
| `src/api/mcp_http.py` | Streamable HTTP `/mcp` server with host allowlist and bearer auth. |
| `src/cli/main.py` | CLI entrypoint (`hermes health`, `providers`, `skills`, `memories`, `remember`, `recall`, `projects`, `ingest`, `run`, `migrate-documents`, `reindex-memory`). |
| `src/memory/store.py` | Safe file-backed `key -> text` storage (`storage/memory`). |
| `src/services/` | `chroma.py`, `chroma_gate.py`, `chunking.py`, `documents.py`, `embed.py`, `embedder.py`, `ingest.py`, `model.py`, `rerank.py`, `workspace.py`. |
| `src/skills/loader.py` | Parses YAML frontmatter + Markdown bodies from `storage/skills/*/SKILL.md`. |
| `src/utils/` | `auth.py`, `logging.py`, `runtime.py`, `settings.py`, `time.py`. |
| `storage/skills/` | 5 concise everyday skills (`autonomous-problem-solver`, `bootstrap-hermes-stack`, `personal-development-coach`, `personal-financial-advisor`, `software-engineering-architect`). |
| `docker/` | `Dockerfile`, `docker-compose.{dev,test,prod,minipc}.yml`, `env/.env.*`, `scripts/{init,build,push,deploy,setup-minipc,bootstrap-gateway,sync-brain,backup-brain,cleanup-disk}.sh`. |
| `scripts/` | `start-local.ps1` (Windows launcher) and `eval_retrieval.py` (RAG eval). |
| `vector-db/` | Chroma 1.0.0 upstream config (`vector-db/config/chroma.yaml`, `vector-db/chromadb/README.md`). |
| `tests/` | Unit tests (`tests/unit/`), contract E2E (`tests/e2e/`), live Chroma integration (`tests/integration/`). |

---

## 4. Personalization Checklist (Before First Run)

Make personal customization cleanly in **configuration and `gateway/USER.md`**, not hardcoded inside Python source:

1. **Identity & Preferences:** Edit `gateway/USER.md` with your preferred name, schedule, communication style, and active focus areas.
2. **Environment & Timezone:** Copy `.env.example` → `.env.local` (for local dev) or `docker/env/.env.prod.example` → `docker/env/.env.prod` (for VPS/Mini PC) and set:
   - `HERMES_TIMEZONE` (e.g., `UTC`, `Asia/Singapore`, `Europe/London`, `America/New_York`, or `UTC+08:00`)
   - `GHCR_OWNER` (GitHub username/org, e.g., `sadramst`, or `local` when building on Mini PC)
   - `HERMES_MCP_ALLOWED_HOSTS` (e.g., `hermes-agent,minipc.tailnet.ts.net,api.hermes.yourdomain.com`)
3. **Mini PC Host Mounts (`docker/env/.env.minipc`):**
   - `HERMES_HOST_PROJECTS_DIR` (absolute host path to your projects directory, default `../workspace`)
   - `HERMES_HOST_KNOWLEDGE_DIR` (absolute host path to your Brain vault / Obsidian notes, default `../knowledge`)
   - `HERMES_WORKSPACE_MODE=rw` (or `ro` for read-only inspection)
4. **Gateway Template Defaults:** Adjust fallback models or optional Telegram DM topic labels in `gateway/config.yaml.example` and schedules in `gateway/cron.yaml.example`.

---

## 5. Local Build, Test & Run Procedure (Windows or Linux/macOS)

### 5.1 Python Environment & Offline Verification (Builder Checklist)

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q -m "not integration"
for s in docker/scripts/*.sh; do bash -n "$s"; done
```

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\pytest -q -m "not integration"
```

Expected: all unit + contract tests pass cleanly (`0` failures; live Chroma integration test is deselected offline), and `git diff --check` exits `0`.

### 5.2 Run Locally on Windows Workstation

1. Copy `.env.example` to `.env.local`, paste `HERMES_MODEL_API_KEY`, and optionally set `HERMES_PROJECTS_DIR` + `HERMES_WORKSPACE_MODE=ro` or `rw`.
2. Optional local Chroma (`:8000`):
   ```powershell
   docker compose --env-file docker/env/.env.dev -f docker/docker-compose.dev.yml up -d chromadb
   ```
3. Start the API (`http://127.0.0.1:8080`):
   ```powershell
   .\scripts\start-local.ps1
   # Or full Docker dev stack:
   .\scripts\start-local.ps1 -Docker
   ```

---

## 6. Mini PC Always-On Home Brain Deployment (Recommended)

Use this mode on a dedicated Ubuntu Server 24.04+ Mini PC to run everything locally (`deploy.sh minipc` overlays `docker-compose.minipc.yml` onto `docker-compose.prod.yml`) with `/workspace` and `/knowledge` mounted cleanly and zero router port-forwarding needed. See [docs/MINIPC_ARCHITECTURE.md](docs/MINIPC_ARCHITECTURE.md) for the complete architecture diagram and BIOS/OS reliability checklist.

### 6.1 Fast One-Command Mini PC Bootstrap

```bash
git clone https://github.com/Sadramst/hermes-agent.git ~/hermes-agent
cd ~/hermes-agent
bash docker/scripts/setup-minipc.sh --no-start
```

What `setup-minipc.sh` does automatically:
- Creates gitignored `docker/env/.env.prod`, `docker/env/.env.gateway`, and `docker/env/.env.minipc` (`chmod 600`).
- Auto-generates random `openssl rand -hex 32` secrets for `CHROMA_AUTH_TOKEN`, `HERMES_API_TOKEN`, and `HERMES_DASHBOARD_BASIC_AUTH_SECRET`.
- Creates host `workspace/`, `knowledge/`, and `backups/` folders and applies `setfacl` permissions for container user `uid=10001` (`hermes`).

### 6.2 Fill API Keys, Host Paths & Start

1. Edit `docker/env/.env.prod`: set `HERMES_TIMEZONE`, `HERMES_MODEL_API_KEY` (+ optional `HERMES_EMBED_API_KEY`), `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`, and add your Tailscale MagicDNS hostname / tunnel domain to `HERMES_MCP_ALLOWED_HOSTS`.
2. Edit `docker/env/.env.gateway`: uncomment **only** keys you actively supply (`OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GOOGLE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`).
3. Edit `docker/env/.env.minipc`: point `HERMES_HOST_PROJECTS_DIR` and `HERMES_HOST_KNOWLEDGE_DIR` to your real folders (or keep defaults `./workspace` and `./knowledge`), choose `HERMES_WORKSPACE_MODE=rw`, and optionally set `CLOUDFLARE_TUNNEL_TOKEN` if using public HTTPS.
4. Build & start everything on the Mini PC:
   ```bash
   bash docker/scripts/deploy.sh minipc
   bash docker/scripts/bootstrap-gateway.sh --force-config
   ```
5. Ingest your Knowledge Vault (`knowledge/`) + projects into ChromaDB:
   ```bash
   bash docker/scripts/sync-brain.sh --projects
   ```

### 6.3 Access From Anywhere Outside the House

1. **Telegram (Zero Setup Ports):** Chat with your bot from anywhere on mobile/desktop. Thanks to shared `/workspace` and `hermes-api` MCP, you can ask Hermes on Telegram to inspect/edit/test any project or search your Brain vault.
2. **Private Mesh VPN via Tailscale (Recommended for Laptop/IDE/Dashboard/SSH):**
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up --ssh
   sudo tailscale serve --bg --https=443 http://127.0.0.1:9119        # Dashboard: https://<node>.<tailnet>.ts.net
   sudo tailscale serve --bg --https=8443 http://127.0.0.1:8569       # API & MCP: https://<node>.<tailnet>.ts.net:8443/mcp/
   ```
   Remember to add `<node>.<tailnet>.ts.net` and `<node>.<tailnet>.ts.net:8443` to `HERMES_MCP_ALLOWED_HOSTS` in `.env.prod` so `/mcp` accepts Tailscale HTTPS requests without returning `421`!
3. **Optional Public HTTPS via Cloudflare Tunnel (`--profile tunnel`):**
   - Create a Cloudflare Zero Trust Tunnel mapping `hermes.yourdomain.com -> http://hermes-gateway:9119` and `api.hermes.yourdomain.com -> http://hermes-agent:8080`.
   - Uncomment `CLOUDFLARE_TUNNEL_TOKEN=<token>` in `docker/env/.env.minipc`, add `api.hermes.yourdomain.com` to `HERMES_MCP_ALLOWED_HOSTS`, and run `bash docker/scripts/deploy.sh minipc`.

---

## 7. Cloud VPS Production Deployment Procedure (`prod`)

For pulling prebuilt GHCR images onto a remote VPS without local builds, follow `deploy.sh prod` (see `docs/DEPLOYMENT.md` for full Docker & Nginx Proxy Manager steps):

```bash
cp docker/env/.env.prod.example docker/env/.env.prod && chmod 600 docker/env/.env.prod
# Fill tokens (`openssl rand -hex 32`), GHCR_OWNER, IMAGE_TAG, and keys
bash docker/scripts/deploy.sh prod
bash docker/scripts/bootstrap-gateway.sh --force-config
```

---

## 8. Telegram Bot, Providers, OAuth & Gemini Subscriptions

### 8.1 Telegram Setup
1. Message `@BotFather` → `/newbot` → obtain `TELEGRAM_BOT_TOKEN`.
2. Optional for domain tabs: `@BotFather` → **Bot Settings** → turn off **Allow Groups?** (personal-only) and enable **Threaded Mode** for DM topics (matching `gateway/config.yaml.example`).
3. Message `@userinfobot` → copy your numeric user ID into `TELEGRAM_ALLOWED_USERS`.
4. Confirm Telegram responds by messaging `/start` or asking *"Check `hermes-api` current time and list memories"*.
5. Set up scheduled briefings using `hermes cron` inside `hermes-gateway` matching `gateway/cron.yaml.example` (schedules follow `TZ=${HERMES_TIMEZONE}`).

### 8.2 Providers & Subscriptions Matrix

| Option | Where | Live Status | Setup |
| --- | --- | --- | --- |
| **OpenRouter** (`google/gemini-2.5-flash` / `~google/gemini-flash-latest`) | API + Gateway | **Live today** | `HERMES_MODEL_API_KEY` (`.env.prod`) + `OPENROUTER_API_KEY` (`.env.gateway`) |
| **Google AI Studio** (`gemini-2.5-flash`, `GOOGLE_API_KEY` / `GEMINI_API_KEY`) | API + Gateway | **Live today (API key)** | API: `HERMES_MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`; Gateway: `GOOGLE_API_KEY` in `.env.gateway` |
| **NVIDIA NIM** (`nvidia/nemotron-3.5-super-vl-120b-a12b`) | Gateway | **Live today** | `NVIDIA_API_KEY` in `.env.gateway` (fallback + context compression) |
| **GitHub Copilot** (`gpt-5.4`) | Gateway | **Live today** | Fine-grained `github_pat_` / `gho_` / `ghu_` in `COPILOT_GITHUB_TOKEN` |
| **Claude Pro / Max** | Gateway | **Live today** | `docker compose ... exec -it hermes-gateway hermes model` → Anthropic OAuth |
| **ChatGPT Plus / Pro** | Gateway | **Live today** | `docker compose ... exec -it hermes-gateway hermes model` → OpenAI Codex OAuth |
| **Nous Portal** | Gateway | **Live today** | `docker compose ... exec -it hermes-gateway hermes setup --portal` |
| **Google Gemini Subscription** | Gateway | **Coming soon (not live yet, no date)** | Waiting on official Nous Research + Google release. **Never** add unofficial consumer-plan bypasses. |

**Upgrade steps once Nous + Google release official Gemini Subscription OAuth:**
1. Pull updated `nousresearch/hermes-agent:latest` and recreate `hermes-gateway`.
2. Run `docker compose ... exec -it hermes-gateway hermes model` and sign in with the official Google flow (persists in `/opt/data/auth.json`).
3. Update `model.provider` in `/opt/data/config.yaml` and optionally `HERMES_PROVIDER_AUTH_MODE` in `.env.prod`.

---

## 9. IDE MCP, Workspace API & CLI Usage

### 9.1 Connect Antigravity / Cursor / Claude MCP
- **Local URL:** `http://127.0.0.1:8080/mcp/` (with `HERMES_MCP_ENABLED=on`, `HERMES_API_TOKEN` set)
- **Mini PC (Tailscale HTTPS):** `https://<node>.<tailnet>.ts.net:8443/mcp/`
- **Public Tunnel / VPS:** `https://<your-api-domain>/mcp/`
- **Header:** `Authorization: Bearer <HERMES_API_TOKEN>`
- **9 Exposed Tools:** `complete`, `current_time`, `list_memories`, `list_skills`, `recall`, `remember`, `save_document`, `search_documents`, `search_memory`

### 9.2 Essential CLI & Workspace Commands
```bash
hermes health
hermes providers
hermes skills
hermes memories --prefix finance.
hermes remember goal.weekly "Ship clean refactor and review budget"
hermes recall goal.weekly
hermes projects
hermes ingest /knowledge --prefix brain
hermes run "Check my weekly goals and open work priorities" --max-steps 4
hermes migrate-documents --from hermes-documents
hermes reindex-memory
```

---

## 10. Runner Verification & Troubleshooting Playbook

### 10.1 Post-Deploy Smoke Checks (Always Run After Starting)
```bash
# 1. API health + workspace + assistant + provider readiness (no secrets leaked)
curl -sS http://127.0.0.1:8569/health

# 2. Provider auth mode + Gemini subscription status (prod / minipc)
curl -sS -H "Authorization: Bearer $HERMES_API_TOKEN" http://127.0.0.1:8569/providers

# 3. Verify workspace projects endpoint
curl -sS -H "Authorization: Bearer $HERMES_API_TOKEN" http://127.0.0.1:8569/projects

# 4. Verify Telegram gateway -> hermes-agent MCP connectivity (must list 9 tools)
docker compose --env-file docker/env/.env.prod --env-file docker/env/.env.gateway \
  -f docker/docker-compose.prod.yml exec hermes-gateway hermes mcp test hermes-api
```
Expected health fields: `status: "ok"`, `chroma.reachable: true`, `assistant.profile_loaded: true`, `mcp.enabled: true`, and (on Mini PC) `workspace.enabled: true`, `workspace.mode: "rw"`.

### 10.2 Backups & Scheduled Sync
```bash
bash docker/scripts/sync-brain.sh --projects
bash docker/scripts/backup-brain.sh --keep 14
```

### 10.3 Common Failures & Exact Fixes
- **`421 Misdirected Request` on `/mcp`:** `Host` header does not match `HERMES_MCP_ALLOWED_HOSTS`. Add your exact Tailscale/Tunnel/domain host (and `:port` if non-standard like `:8443`) to `HERMES_MCP_ALLOWED_HOSTS` (max 8 entries) and ensure any proxy preserves the `Host` header.
- **Permission denied writing `/workspace/<project>` in `minipc`:** Container runs as `uid=10001`. Re-run `bash docker/scripts/setup-minipc.sh --no-start` (sets `setfacl -m u:10001:rwx`) or `sudo setfacl -R -m u:10001:rwx -d -m u:10001:rwx ~/hermes-agent/workspace`.
- **Telegram or OAuth token disappears on restart:** Either a blank variable was left uncommented in `.env.gateway` or `/opt/data` volume wasn't synced cleanly. Keep unused lines commented out in `.env.gateway`.
- **`chroma.reachable: false` in prod/minipc:** Check `CHROMA_AUTH_TOKEN` matches across `.env.prod` interpolation (`hermes-agent`, `chromadb`, `chroma-gate`) and inspect `docker compose logs chroma-gate chromadb`.
- **Documents uploaded before enabling embeddings missing from v2 searches:** Switching `HERMES_EMBED_*` moves collections to `hermes-documents-v2` / `hermes-memory-v2`. Run `hermes migrate-documents --from hermes-documents` and `hermes reindex-memory`.
- **`Bash` syntax error `\r` on Ubuntu scripts:** Normalize line endings (`sed -i 's/\r$//' docker/scripts/*.sh`) and verify `bash -n`.
- **Disk filling up from old layers:** Run `bash docker/scripts/cleanup-disk.sh --dry-run` then `bash docker/scripts/cleanup-disk.sh` (preserves named volumes).
