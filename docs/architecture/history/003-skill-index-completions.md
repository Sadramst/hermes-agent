# Architecture after the completion skill index

Date: 2026-10-19

`POST /completions` still sends one chat completion. Hermes code loads the skill index and prefixes it onto the caller's prompt. Jev is not in the running stack.

```mermaid
flowchart TB
  subgraph host ["Host"]
    envFiles["docker/env/.env.dev | .env.test | .env.prod"]
  end

  subgraph net ["Docker network hermes-net"]
    agent["hermes-agent\ncap_drop ALL\nGET /health :8080"]
    chroma["chromadb\n:8000"]
  end

  skillsVol["skills\n/app/storage/skills"]
  provider["model provider"]

  envFiles --> agent
  agent --> skillsVol
  agent -->|"skill index + prompt"| provider
  agent -->|"HTTP heartbeat"| chroma
```
