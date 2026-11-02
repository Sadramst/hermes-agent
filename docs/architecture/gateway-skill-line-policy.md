# Gateway skill-line policy (standing instruction)

Paste the block below into the Hermes gateway identity file so Telegram (and dashboard chat) can ask the Python API for the same advisory skill line Hermes uses in soft completions.

**Where it lives on the server:** the gateway volume file `SOUL.md` under Hermes home (production Docker: inside `hermes-prod-gateway` at `/opt/data/SOUL.md`).

**Production status (2026-10-21):** applied on `5011-Hermes` gateway `SOUL.md` (includes `## Skill suggestion (API)` / `suggest_skill`). Re-paste only after a volume wipe or a fresh gateway home.

**Do not** put secrets, tokens, or host IPs in this policy. Tool names may use the MCP server name `hermes-api`.

---

## Skill suggestion (API)

When choosing among this gateway's skills for the user's latest message (or early in the turn when a skill might apply):

1. Call `hermes-api` tool `suggest_skill` with:
   - `request`: the user's latest message
   - `skills`: this gateway's roster as objects `{ "name", "description" }` (optional `version`)
2. Read the JSON result. If `available` is true and `line` is non-empty, treat `line` as advisory context for this turn. You may ignore it if it does not fit.
3. Do **not** replace this gateway's generative model with Jev. Hermes API remains the judge; you remain the agent.

If `available` is false or `line` is empty, continue without an advisory line.
