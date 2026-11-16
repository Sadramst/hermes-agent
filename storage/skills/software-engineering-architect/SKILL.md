---
name: software-engineering-architect
version: 1.0.0
---
# Purpose

Assist with everyday software engineering, debugging, code review, system design, testing, Docker, and server automation across any repository or environment.

# Inputs

- Code question, bug report, architecture choice, or deployment troubleshooting task
- Stored engineering context (`list_memories` prefix `dev.` / `work.` / `ops.`, `search_documents`)

# Outputs

- Root-cause diagnosis, clean implementation steps, minimal diffs, or verified CLI commands
- Durable engineering decisions saved under `dev.*`, `work.*`, or `ops.*` when useful

# Execution flow

1. Check `list_memories` (`work.`, `dev.`, `ops.`) and `search_documents` for existing project conventions and environment setup.
2. Inspect real files and tests before suggesting changes; preserve existing test contracts (`pytest -q -m "not integration"` and shell syntax checks).
3. Keep secrets out of git (`.env.local`, `.env.prod`, `.env.gateway`) and maintain least-privilege container defaults (`cap_drop: ALL`).
4. Before destructive infrastructure or database commands (`--volumes`, `delete_memory`, force resets), summarize the blast radius and ask for explicit confirmation.

# Error handling

- If project context or server details are absent from memory/files, ask or state the gap clearly instead of guessing paths or credentials.

# Logging

Standard `hermes` audit events (`tools.run`, `memory.read`, `memory.write`) without logging code secrets.

# Versioning

Bump when shared engineering workflows or operational safety rules change.

# Test coverage

- `tests/e2e/test_stack_contract.py`
- `tests/unit/test_personal_assistant.py`

# Documentation references

- `AGENTS.md`
- `docs/DEPLOYMENT.md`
- `README.md`
