# Document search policy for gateway SOUL.md

The Nous gateway (`hermes-gateway`) reaches Hermes documents through the MCP server `hermes-api` at `http://hermes-agent:8080/mcp/`. It has no vector store of its own and does not need one. Paste the block below into the gateway `SOUL.md`, next to the shared-memory policy in [shared-memory-policy.md](shared-memory-policy.md) and the skill line in [gateway-skill-line-policy.md](gateway-skill-line-policy.md).

The gateway model still writes the reply. Hermes only returns passages.

## Register the server

The gateway stores MCP servers in `/opt/data/config.yaml` on the volume `hermes-prod-gateway`. That file stays out of git. When the volume is new, add this entry under `mcp_servers`. Compose already passes `HERMES_API_TOKEN` into the gateway, and Hermes expands `${HERMES_API_TOKEN}` on each connect. Leave the placeholder in the file.

```yaml
mcp_servers:
  hermes-api:
    url: http://hermes-agent:8080/mcp/
    headers:
      Authorization: "Bearer ${HERMES_API_TOKEN}"
    enabled: true
```

Use the Docker service name `hermes-agent`. The public hostname times out from inside the gateway. Confirm with `hermes mcp test hermes-api` inside `hermes-gateway`. A connected server lists `search_documents` and `search_memory`. Start a new chat after the entry appears. An open session keeps the tool list it started with.

`HERMES_MCP_ENABLED=on` is required on `hermes-agent`. While it is `off`, `/mcp` answers 404.

## Paste block

```text
## Hermes documents

For a question about our servers, ports, deployments, or procedures, call MCP server `hermes-api`, tool `search_documents`, once. Pass the question as `q`. Answer from that result and cite its `[label]`. If it returns no match, say so.

Do not use the terminal, curl, file search, sqlite, or session search for this, and do not call another tool after `search_documents`.

When you do not know a memory key, call `hermes-api` `search_memory` once, then `recall` with the key it returns.
```

## Check it

1. Save a document: `POST /documents` with `{"id": "restore", "text": "...", "source": "runbook.md"}`.
2. Ask the gateway "How do I restore the Hermes stack?" in the browser chat.
3. The reply cites `[restore::0000]`. The gateway logs show one `mcp__hermes_api__search_documents` call.

`search_memory` answers `Memory search is off` until `HERMES_MEMORY_INDEX=on`.
