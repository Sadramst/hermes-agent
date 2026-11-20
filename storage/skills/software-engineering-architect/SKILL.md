---
name: software-engineering-architect
version: 1.0.0
---
# Purpose

Assist with everyday software engineering, debugging, code review, system design, testing, Docker, and multi-project workspace operations across any repository or environment.

# Inputs

- Code question, bug report, architecture choice, or multi-project command task
- Stored engineering context (`list_memories` prefix `dev.` / `work.` / `ops.`, `search_documents`) and active workspace tools (`list_projects`, `list_project_files`, `read_project_file`, `search_project`, `write_project_file`, `run_project_command`)

# Outputs

- Root-cause diagnosis, clean implementation steps, minimal verified edits, or CLI/test outputs
- Durable engineering decisions saved under `dev.*`, `work.*`, or `ops.*` when useful

# Execution flow

1. Inspect `list_projects` and read real files (`list_project_files`, `read_project_file`, `search_project`) plus `list_memories` (`work.`, `dev.`, `ops.`) before proposing or applying edits.
2. After modifying code via `write_project_file`, verify with tests and `git status` / `git diff` via allowlisted `run_project_command`.
3. Keep secrets out of git (`.env.local`, `.env.prod`, `.env.gateway`, `.env.minipc`) and never access secret files or bypass `cap_drop: ALL`.
4. Before destructive infrastructure, force-git, or delete operations (`--volumes`, `delete_memory`, `git reset --hard`, `git push --force`), summarize the blast radius and ask for explicit confirmation.

# Error handling

- If project context, target directory, or runtime binary is missing, state the exact gap instead of guessing paths or credentials.

# Logging

Standard `hermes` audit events (`tools.run`, `workspace.write`, `workspace.exec`, `memory.read`, `memory.write`) without logging code secrets.

# Versioning

Bump when shared engineering workflows, workspace tools, or operational safety rules change.

# Test coverage

- `tests/unit/test_workspace.py`
- `tests/e2e/test_stack_contract.py`
- `tests/unit/test_personal_assistant.py`

# Documentation references

- `AGENTS.md`
- `docs/MINIPC_ARCHITECTURE.md`
- `docs/DEPLOYMENT.md`
- `README.md`
