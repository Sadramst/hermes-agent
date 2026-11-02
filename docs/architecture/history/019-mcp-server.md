# Architecture after the Cursor MCP server

Date: 2026-10-20

`HERMES_MCP_ENABLED` defaults to `off`. While it is off, `/mcp` answers 404. When it is `on`, Cursor calls a streamable HTTP MCP server on that path with `Authorization: Bearer <HERMES_API_TOKEN>`. The tools are `list_skills`, `recall`, `remember`, `search_documents`, and `complete`. `delete_memory` is absent. `complete` still uses `HERMES_MODEL_NAME`. Hermes does not call Cursor and does not use Cursor's LLM. Health reports `mcp.enabled` and still omits tokens. Sixty requests in sixty seconds answer 429.

```mermaid
flowchart LR
  cursor["Cursor MCP client"]
  agent["hermes-agent\n/mcp"]
  provider["HERMES_MODEL_NAME"]
  cursor -->|"bearer token"| agent
  agent -->|"complete"| provider
```
