---
name: autonomous-problem-solver
version: 1.1.0
---
# Purpose

Solve everyday multi-step requests accurately by checking time, memory, documents, and skills first, saving lasting findings under dotted keys, and giving grounded answers.

# Inputs

- User request and loaded `USER.md` / `SOUL.md` preferences
- Clock (`current_time`), skills (`list_skills`, `read_skill`), memory (`list_memories`, `search_memory`, `recall`, `remember`), and documents (`search_documents`, `save_document`)

# Outputs

- Executed tool trace (`steps`) and concise grounded response citing `[label]` for any retrieved document passage
- Lasting user facts persisted via `remember` (`profile.*`, `work.*`, `dev.*`, `goal.*`, `habit.*`, `study.*`, `finance.*`, `ops.*`) or `save_document`

# Execution flow

1. Call `current_time` whenever dates, weekdays, schedules, or periods matter.
2. Check `list_memories`, `search_memory`, or `search_documents` before guessing prior preferences, facts, or plans.
3. If a loaded skill fits the task, call `read_skill` to follow its guardrails and checklist.
4. Persist confirmed durable facts or reference notes via `remember` or `save_document`.
5. Reply concisely, citing `[label]` for retrieved passages.

# Error handling

- State clearly when no memory or document matches instead of inventing facts.
- Stop and wait for human confirmation if an irreversible tool (`delete_memory`) returns `ask_person`.

# Logging

Tool calls log under `hermes` (`tools.run name=<tool> status=<status> env=<HERMES_ENV>`) without prompt text or argument secrets.

# Versioning

Skill version `1.1.0` tracks the generic multi-step tool loop and dotted memory layout.

# Test coverage

- `tests/unit/test_autonomous_loop.py`
- `tests/unit/test_personal_assistant.py`

# Documentation references

- `AGENTS.md`
- `README.md`
