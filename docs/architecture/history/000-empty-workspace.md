# Architecture before the container stack

Date: 2026-09-25

The workspace had no source tree, no Compose files, and no running services.

```mermaid
flowchart LR
  subgraph repo ["hermes-agent"]
    empty["Empty workspace"]
  end
```

No network, volume, or image existed yet.
