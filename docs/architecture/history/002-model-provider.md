# Architecture after the model provider

Date: 2026-10-18

The agent sends completion requests to a provider configured by environment variables. Document and completion routes require `HERMES_API_TOKEN` in production. The agent container drops all Linux capabilities after the startup check.

```mermaid
flowchart TB
  subgraph host ["Host"]
    envFiles["docker/env/.env.dev | .env.test | .env.prod"]
  end

  subgraph net ["Docker network hermes-net"]
    agent["hermes-agent\ncap_drop ALL\nGET /health :8080"]
    chroma["chromadb\n:8000"]
  end

  provider["model provider"]

  envFiles --> agent
  agent -->|"completion request"| provider
  agent -->|"HTTP heartbeat"| chroma
```
