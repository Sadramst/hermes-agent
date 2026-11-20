# User Profile

Edit this file directly or ask Hermes in chat to update your preferences over time. Never put passwords, API keys, bank logins, card numbers, or tokens here.

## Identity & Preferences
- **Name / Handle:** Sadra Tabarestani (`Sadramst`)
- **Primary Timezone:** Uses active `HERMES_TIMEZONE` setting (update `.env.*` when travelling)
- **Preferred Style:**
  - Direct answer or concrete next step first; concise reasoning
  - Checklists and short tables for complex choices
  - Mobile-friendly, scannable formatting in Telegram
  - Explicit risk/assumption callouts before irreversible actions

## Everyday Focus Areas
1. **Work & Engineering:** Managing active software repositories, AI workflows, architecture, debugging, and shipping across `/workspace` on the Mini PC and laptops remotely.
2. **Personal Growth & Daily Execution:** Deep work blocks, practical learning notes synced via `/knowledge` + Brain RAG, consistent health/fitness habits, and weekly reviews.
3. **Personal Finance Organization:** Clear cashflow visibility, emergency runway, savings targets, and risk-aware decision comparisons (analytical only — never autonomous money movement).
4. **Life Admin & Knowledge Capture:** Research synthesis, travel/errands planning, writing, and searchable long-term memory across all devices.

## Infrastructure Context (Mini PC Home Brain)
- **Always-On Brain Host:** Mini PC (Ubuntu Server 24.04 LTS, Docker Compose `minipc` profile)
- **Mounted Directories:**
  - Projects Workspace: `/workspace` (mapped from host `HERMES_HOST_PROJECTS_DIR`, `rw` mode with safety allowlist)
  - Personal Knowledge Vault: `/knowledge` (mapped read-only from host `HERMES_HOST_KNOWLEDGE_DIR`, indexed into ChromaDB)
- **Access From Anywhere:** Telegram (`hermes-gateway`), Tailscale private mesh VPN (`hermes-dashboard` / API / `/mcp`), optional Cloudflare Tunnel HTTPS, and remote IDE MCP (`Antigravity` / `Cursor`)
- **Shared Memory Prefixes (`hermes-api`):** `profile.*`, `work.*`, `dev.*`, `goal.*`, `habit.*`, `study.*`, `finance.*`, `ops.*`
