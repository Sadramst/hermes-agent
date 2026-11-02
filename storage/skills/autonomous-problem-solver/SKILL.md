---
name: autonomous-problem-solver
version: 1.0.0
---
# Purpose

Solve multi-step user requests autonomously by searching memory and documents first, reading relevant skills, storing durable findings, and synthesizing a cited answer.

# Inputs

- User prompt or task description
- Loaded skill index (`list_skills`, `read_skill`)
- Persistent memory store (`search_memory`, `recall`, `remember`)
- ChromaDB document store (`search_documents`, `save_document`)

# Outputs

- Executed tool call trace (`steps`)
- Grounded assistant response (`text`) citing `[label]` for any retrieved document passages
- Durable facts persisted to memory when requested by the user

# Execution flow

1. Check if the request references prior preferences, server facts, or runbooks; call `search_memory` or `search_documents` before guessing.
2. When a skill in the index matches the task, call `read_skill` to inspect its detailed procedure.
3. When the user provides new durable facts or preferences, call `remember` with a clear, stable key (or `save_document` for longer reference notes).
4. Synthesize a concise, accurate final answer after gathering evidence from tool outputs.

# Error handling

- If `search_documents` or `search_memory` returns no matches, state clearly that no stored records matched instead of fabricating facts.
- If an irreversible tool (`delete_memory`) returns `ask_person`, report that human confirmation is required and stop calling tools.
