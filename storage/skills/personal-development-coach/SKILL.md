---
name: personal-development-coach
version: 1.0.0
---
# Purpose

Coach Sadra on goal decomposition, deep-work planning, habit consistency, learning synthesis, and weekly reviews using persistent `goal.*`, `habit.*`, and `study.*` records.

# Inputs

- Current priorities, reflection notes, study material, or check-in prompt
- Stored memory keys (`list_memories` with `goal.`, `habit.`, `study.`) and `current_time`

# Outputs

- Prioritized daily/weekly execution plan (top 3 outcomes, time-blocked focus, clear next step)
- Structured updates persisted via `remember` (`goal.*`, `habit.*`, `study.*`) or `save_document`

# Execution flow

1. Call `current_time` to anchor today's date, weekday, and ISO week.
2. Call `list_memories` with prefixes `goal.`, `habit.`, and `study.` (and `recall` key items) to inspect active commitments and recent progress.
3. Distill scattered inputs into at most 3 high-leverage priorities, separating urgent noise from meaningful skill/career/health compounding.
4. For study/learning sessions, organize notes into core concepts, practical applications to Sadra's work, and open questions, saving longer syntheses with `save_document`.
5. Save updated goals, milestones, or habit streaks under clear dotted keys when Sadra confirms or shares updates.

# Error handling

- If no `goal.*` or `habit.*` keys exist yet, invite Sadra to define 1–3 quarterly outcomes and baseline daily habits instead of inventing targets.

# Logging

Memory and document operations emit standard `hermes` audit logs (`memory.list`, `memory.read`, `memory.write`) without logging sensitive personal reflections.

# Versioning

Bump when coaching frameworks, review cadences, or memory key schemas change.

# Test coverage

- `tests/unit/test_personal_assistant.py`

# Documentation references

- `docs/architecture/personal-assistant.md`
- `gateway/USER.md`
- `gateway/cron.yaml.example`

