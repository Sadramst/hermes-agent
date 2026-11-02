# Architecture history

Snapshots of the Hermes Agent architecture live in this folder.

| Snapshot | State |
| --- | --- |
| [000-empty-workspace.md](000-empty-workspace.md) | Repository before the container stack |
| [001-containerized-stack.md](001-containerized-stack.md) | DEV, TEST, and PROD stack with ChromaDB |
| [002-model-provider.md](002-model-provider.md) | Model provider, API credential, and capability drop |
| [003-skill-index-completions.md](003-skill-index-completions.md) | Completions prefix the loaded skill index onto the caller prompt |
| [004-jev-client-shadow.md](004-jev-client-shadow.md) | Jev client, health fields, and decision plumbing. Mode defaults to off |
| [005-skill-suggestion-shadow.md](005-skill-suggestion-shadow.md) | Shadow skill suggestion logs a winner and leaves the completion prompt unchanged |
| [006-skill-suggestion-advisory.md](006-skill-suggestion-advisory.md) | Soft mode adds a skill_relevance block the model may ignore |
| [007-chroma-passage-shadow.md](007-chroma-passage-shadow.md) | Search logs a chroma-passage judgment and still returns every neighbor |
| [008-chroma-passage-soft.md](008-chroma-passage-soft.md) | Soft search returns passages at the helping relevance level |
| [009-guardrails-shadow.md](009-guardrails-shadow.md) | Completions log a guardrails route and still return the model text |
| [010-guardrails-soft.md](010-guardrails-soft.md) | Soft mode withholds the model reply on review or block |
| [011-memory-write-shadow.md](011-memory-write-shadow.md) | Memory writes log a kind and still store the record |
| [012-memory-write-soft.md](012-memory-write-soft.md) | Soft mode skips one-shot memory writes |
| [013-tool-runner.md](013-tool-runner.md) | The tool runner executes an allowlist and asks a person before an irreversible tool |
| [014-tool-gate-shadow.md](014-tool-gate-shadow.md) | Shadow logs a tool-call judgment and still runs the allowlist |
| [015-tool-gate-soft.md](015-tool-gate-soft.md) | Soft mode holds a tool call unless Jev picked it and the score is clear |
| [016-model-router-shadow.md](016-model-router-shadow.md) | The model router logs a tier and the completion stays on the frontier model |
| [017-supervisor-shadow.md](017-supervisor-shadow.md) | The supervisor logs a loop and a completion judgment and leaves the result unchanged |
| [018-supervisor-soft.md](018-supervisor-soft.md) | Soft mode stops tool calls that follow a looping judgment and leaves the completion text unchanged |
| [019-mcp-server.md](019-mcp-server.md) | Cursor can call `/mcp` when `HERMES_MCP_ENABLED` is `on`. The route defaults to off |
| [020-grok-handoff.md](020-grok-handoff.md) | `delegate_to_grok` can post one task when `HERMES_GROK_HANDOFF` is `on`. The mode defaults to off |
| [021-retrieval.md](021-retrieval.md) | Documents are chunked and cited, search fuses a keyword ranking, and `HERMES_RAG_MODE` can add a Context block to completions. The mode defaults to off |

The big picture is [../overview.md](../overview.md). The live description is [../current.md](../current.md). The numbered plan is done through soft promotion on production. Frontier comparison, smaller-model switch code, gateway skill-line MCP + SOUL, and the Grok channel are shipped; see [../planned.md](../planned.md). Optional leftover: set `HERMES_MODEL_SMALL` when you want soft completions to use a cheaper model on `small`/`ok`.
