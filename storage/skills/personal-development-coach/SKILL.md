---
name: personal-development-coach
version: 1.0.0
---
# Purpose

Support everyday productivity, goal setting, habit consistency, structured learning notes, health routines, and life admin using `goal.*`, `habit.*`, and `study.*` records.

# Inputs

- Daily priorities, reflections, reading/study notes, habit check-ins, or life-admin requests
- Current local time (`current_time`) and stored `goal.`, `habit.`, `study.` memory keys

# Outputs

- Realistic daily/weekly execution plan (top priorities, focus blocks, next action) or clean study/life synthesis
- Confirmed updates saved via `remember` or `save_document`

# Execution flow

1. Call `current_time` to anchor today's date, weekday, and week number.
2. Inspect `list_memories` (`goal.`, `habit.`, `study.`) and `USER.md` preferences before suggesting plans.
3. Distill busy lists into at most 3 high-leverage priorities and clear, concrete next actions.
4. Summarize learning materials into key ideas, practical takeaways, and open questions, saving longer notes with `save_document`.
5. Persist updated goals or habit check-ins when the user shares or confirms them.

# Error handling

- If no prior `goal.*` or `habit.*` entries exist, ask the user for 1–3 focus areas rather than inventing goals.

# Logging

Memory and document operations emit standard `hermes` key-level audit logs without private journal contents.

# Versioning

Bump when everyday planning frameworks or memory conventions change.

# Test coverage

- `tests/unit/test_personal_assistant.py`

# Documentation references

- `AGENTS.md`
- `gateway/USER.md`
- `gateway/cron.yaml.example`
