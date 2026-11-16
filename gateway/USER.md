# User Profile — Sadra Tabarestani (`Sadramst`)

Customize this file directly or ask Hermes over Telegram / Dashboard to refine sections as your goals, stack, and priorities evolve. Do **not** store passwords, API keys, bank credentials, or secret tokens here.

## Identity & Environment
- **Name / Handle:** Sadra Tabarestani (`Sadramst`)
- **Primary Domain:** `sadramst.dev` (`hermes.sadramst.dev` dashboard, `api.hermes.sadramst.dev` API/MCP)
- **GitHub / Registry:** `github.com/Sadramst` / `ghcr.io/sadramst/hermes-agent`
- **Workstations & Hosts:**
  - Local development: Windows workstation (`.venv`, PowerShell `scripts/start-local.ps1`, Antigravity / Cursor IDE)
  - Always-on production server: Ubuntu 24.04+ VPS running Docker Compose (`hermes-agent`, `hermes-gateway`, `chroma-gate`, `chromadb`)
- **Timezone:** `UTC+08:00` (`Asia/Singapore` / `HERMES_TIMEZONE` — adjust in `.env.prod` / `.env.local` if travelling)

## Communication Preferences
- Lead with the direct answer, action, or recommendation first; keep reasoning concise and structured.
- Use checklists, tables, and concrete next actions for complex engineering, life, or financial decisions.
- Call out assumptions, risks, and irreversible actions before executing.
- Keep Telegram responses crisp and mobile-readable (short paragraphs, scannable bullets, no walls of filler text).

## Focus Pillars
1. **Work & Software Engineering:** Building reliable AI agent systems, backend APIs, DevOps/VPS automation, clean testing, and shipping personal/client software efficiently.
2. **Personal Development:** Deep work discipline, technical mastery, structured learning notes, consistent health/sleep/exercise habits, and weekly reflection.
3. **Personal Financial Advisory & Planning:** Clear cashflow visibility, emergency runway tracking, disciplined savings/investing frameworks, major-purchase modeling, and risk-aware decision support (advisory only — zero autonomous transactions).
4. **Daily Operations & Life Admin:** Proactive Telegram reminders, reading/research capture, and keeping cross-tool context synced.

## Shared Memory Namespace Conventions (`hermes-api`)
When storing facts in `hermes-api` (`remember`), prefer predictable dotted keys:
- `profile.*` — Core personal preferences, timezone, hardware/workspace notes
- `work.*` — Active projects, architecture decisions, client/team context
- `dev.*` — Tooling conventions, CI/CD rules, debugging lessons
- `goal.*` — Quarterly objectives, weekly top priorities, milestones
- `habit.*` — Routines, health/fitness targets, review cadence
- `finance.*` — Budget targets, runway assumptions, non-sensitive portfolio allocation frameworks (never credentials or account numbers)
- `ops.*` — VPS ports, domains, backup routines, non-secret runbook notes

