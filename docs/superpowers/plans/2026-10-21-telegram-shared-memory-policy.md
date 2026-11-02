# Telegram shared-memory policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Telegram prefer the shared Hermes API memory tools (`hermes-api` MCP) for lasting facts, using gateway config only.

**Architecture:** Track a short canonical policy in this repo. Append that text to the live gateway `SOUL.md` on the production volume so every Telegram session injects it. Verify with an unprompted remember on Telegram and a recall on Grok.

**Tech Stack:** Hermes gateway `SOUL.md` (Docker volume `hermes-prod-gateway` → `/opt/data`), existing MCP server `hermes-api` → `http://hermes-agent:8080/mcp/`, Markdown docs in this repository.

## Global Constraints

- No Python API code changes for this feature
- No secrets, tokens, or private IPs in `SOUL.md` or committed docs
- Keep the existing SOUL personality text; append the Shared knowledge sections
- MCP URL for the gateway stays `http://hermes-agent:8080/mcp/` (do not switch back to the public hostname)
- Canonical wording must match `docs/architecture/shared-memory-policy.md`

---

### Task 1: Confirm canonical policy is in git

**Files:**
- Verify: `docs/architecture/shared-memory-policy.md`
- Verify: `docs/superpowers/specs/2026-10-21-telegram-shared-memory-policy-design.md`
- Verify: `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md`

**Interfaces:**
- Consumes: none
- Produces: stable copy-paste block titled `## Shared knowledge (API)` through `## When unsure`

- [ ] **Step 1: Open the canonical policy file**

Confirm these three headings exist exactly:

```markdown
## Shared knowledge (API)
## Local gateway memory
## When unsure
```

- [ ] **Step 2: Confirm MCP server name**

The policy must tell the model to use server `hermes-api` and tools `remember`, `recall`, and `search_documents`. If the live dashboard renamed the server, update the canonical file to the live name before pasting.

- [ ] **Step 3: Commit docs if not already committed**

```bash
git add docs/architecture/shared-memory-policy.md \
  docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md \
  docs/superpowers/specs/2026-10-21-telegram-shared-memory-policy-design.md \
  docs/superpowers/plans/2026-10-21-telegram-shared-memory-policy.md
git commit -m "$(cat <<'EOF'
docs: plan Telegram preference for shared Hermes API memory

EOF
)"
```

Only run the commit when the user asked for a commit or already approved committing these docs.

---

### Task 2: Append policy to live gateway SOUL.md

**Files:**
- Modify on server: `/opt/data/SOUL.md` inside container `hermes-gateway` (volume `hermes-prod-gateway`)
- Source text: `docs/architecture/shared-memory-policy.md` (sections under the horizontal rule)

**Interfaces:**
- Consumes: canonical policy sections from Task 1
- Produces: gateway SOUL that includes Shared knowledge rules for every new session

- [ ] **Step 1: SSH to the host and locate SOUL.md**

```bash
cd /opt/hermes-agent
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml exec hermes-gateway \
  sh -c 'ls -la /opt/data/SOUL.md; wc -c /opt/data/SOUL.md'
```

Expected: file exists and size is greater than 0. If missing, create it with a one-line identity first, then append the policy.

- [ ] **Step 2: Backup the current SOUL**

```bash
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml exec hermes-gateway \
  sh -c 'cp /opt/data/SOUL.md /opt/data/SOUL.md.bak-$(date +%Y%m%d)'
```

Expected: backup path printed or `ls` shows the `.bak-` file.

- [ ] **Step 3: Check whether the policy is already present**

```bash
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml exec hermes-gateway \
  sh -c 'grep -n "Shared knowledge (API)" /opt/data/SOUL.md || true'
```

Expected if not applied: empty output. If a match exists, skip Step 4 and go to Task 3.

- [ ] **Step 4: Append the canonical sections**

From a machine that has the repo text, copy only the three sections from `docs/architecture/shared-memory-policy.md` (from `## Shared knowledge (API)` through the end of `## When unsure`). On the server, append them after a blank line at the end of `/opt/data/SOUL.md`.

Example using a here-doc inside the container (adjust if `sh` lacks the heredoc; then use `docker cp` instead):

```bash
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml exec -T hermes-gateway \
  sh -c 'cat >> /opt/data/SOUL.md' <<'EOF'

## Shared knowledge (API)

Facts that must be visible to Grok, Cursor, Telegram, and any other MCP client belong in the Hermes API key-value store and document search.

- To save a lasting fact: call the MCP tools on server `hermes-api` — `remember` with a short stable key and the value.
- To read a lasting fact: call `hermes-api` `recall` with that key.
- To search saved documents: call `hermes-api` `search_documents`.
- Prefer those tools whenever the user asks to remember, recall, or share knowledge across channels.

## Local gateway memory

The built-in gateway memory tools and `MEMORY.md` / `USER.md` stay on this gateway only. Use them for persona notes and session preferences that must not leave this gateway. Do not use them for facts that should be shared with Grok or Cursor.

## When unsure

If a fact should still be true tomorrow for both Telegram and Grok, use `hermes-api` `remember`. Say which tool you used when you confirm the save.
EOF
```

- [ ] **Step 5: Verify the append**

```bash
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml exec hermes-gateway \
  sh -c 'tail -n 40 /opt/data/SOUL.md'
```

Expected: the three headings appear at the end of the file.

- [ ] **Step 6: Restart the gateway so messaging sessions reload SOUL**

```bash
docker compose --env-file docker/env/.env.prod \
  -f docker/docker-compose.prod.yml restart hermes-gateway
```

Expected: container returns to healthy / running. Dashboard at `https://hermes.newplanetit.com.au` loads again.

---

### Task 3: Prove unprompted shared remember (Telegram → Grok)

**Files:**
- None in git
- Uses live Telegram + Grok + API memory key `office-wifi-hint` (or another unused key)

**Interfaces:**
- Consumes: SOUL policy from Task 2; MCP `hermes-api` tools
- Produces: API memory key readable by Grok without Telegram naming MCP

- [ ] **Step 1: Confirm MCP still lists five tools**

In the dashboard **MCP** page, open `hermes-api` and click **Test**.

Expected tools: `list_skills`, `recall`, `remember`, `search_documents`, `complete`.

- [ ] **Step 2: Send Telegram a remember request that does not name MCP**

Exact message:

```text
Remember for everyone that the office wifi password hint is blue-orchid-7. Use key office-wifi-hint.
```

Do not mention `hermes-api`, MCP, or `remember` as a tool name beyond normal English.

- [ ] **Step 3: Read Telegram’s confirmation**

Pass criteria:

- Confirmation shows the shared MCP path (for example `mcp__hermes_api__remember` or wording that names `hermes-api`)
- Fail if it only used the built-in gateway memory tool with no MCP call

- [ ] **Step 4: Ask Grok to recall the same key**

Exact message:

```text
Use the Hermes tool recall with key office-wifi-hint.
```

Expected value: `blue-orchid-7` or a sentence that clearly contains that hint.

- [ ] **Step 5: Record the result in the roadmap status**

In `docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md`, under **Done**, add one bullet:

```markdown
- Telegram SOUL shared-memory policy applied; unprompted remember key `office-wifi-hint` readable from Grok
```

- [ ] **Step 6: Commit the roadmap status update (when the user asks to commit)**

```bash
git add docs/superpowers/specs/2026-10-21-shared-knowledge-roadmap.md
git commit -m "$(cat <<'EOF'
docs: mark Telegram shared-memory policy verified

EOF
)"
```

---

### Task 4: Optional negative check (persona-only note)

**Files:** none

**Interfaces:**
- Consumes: same SOUL policy
- Produces: confidence that local memory remains available for non-shared notes

- [ ] **Step 1: Send Telegram a persona-only note**

```text
For this gateway only, note that I prefer short Telegram replies. Do not share that preference with Grok.
```

- [ ] **Step 2: Ask Grok whether a shared key exists for that preference**

```text
Recall key telegram-reply-style if it exists.
```

Pass criteria: Grok does not return a shared fact invented for that preference (missing key / empty is fine). If Telegram created a shared key anyway, tighten the SOUL wording and repeat Task 3 with a new key.

---

## Self-review

1. **Spec coverage:** Problem, SOUL append, verification Telegram→Grok, and non-goals are all tasked.
2. **Placeholders:** None; exact messages, paths, and commands are filled.
3. **Consistency:** MCP server name `hermes-api`, tools `remember`/`recall`/`search_documents`, and volume path `/opt/data/SOUL.md` match the design and canonical policy file.
