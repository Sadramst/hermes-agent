# Docker deployment

## Prerequisites

Docker Engine with Compose v2, and a published runtime image for production. A beginner walkthrough for Ubuntu Server 24.04 and newer, from cloning the repository through dev, test, and production, is in [ubuntu-server.md](ubuntu-server.md).

## Persistent storage

| Data | Container path | DEV | TEST | PROD |
| --- | --- | --- | --- | --- |
| Memory | `/app/storage/memory` | Bind mount `storage/memory` | tmpfs | Named volume `hermes-prod-memory` |
| Skills | `/app/storage/skills` | Bind mount `storage/skills` | tmpfs | Named volume `hermes-prod-skills` |
| Embeddings | `/data` | Named volume `hermes-dev-chroma` | tmpfs | Named volume `hermes-prod-chroma` |

The first time a named skills volume is created, Docker seeds it from the skill files copied into the image, including `bootstrap-hermes-stack`.

## Network

Each environment creates a bridge network named `hermes-<environment>-net`. Compose attaches both services to the network key `hermes-net`. The agent reaches Chroma at `http://chromadb:8000`.

## Start and stop

From the repository root:

```bash
docker/scripts/init.sh
docker/scripts/deploy.sh dev
docker/scripts/deploy.sh test
docker/scripts/deploy.sh prod
```

`dev` builds the runtime image, mounts source for reload, and listens on `http://127.0.0.1:8080/health`. Chroma is published on port 8000.

`test` starts Chroma and the agent with tmpfs storage, then runs `pytest -m "not integration"` in `hermes-tests`. The Compose command exits with the test container's status. Test publishes no host ports.

`prod` pulls `ghcr.io/${GHCR_OWNER}/hermes-agent:${IMAGE_TAG}` and starts it with named volumes. Set `GHCR_OWNER`, `IMAGE_TAG`, `CHROMA_AUTH_TOKEN`, `HERMES_API_TOKEN`, `HERMES_MODEL_BASE_URL`, `HERMES_MODEL_NAME`, and `HERMES_MODEL_API_KEY` in `docker/env/.env.prod` before deploying. Generate each token with `openssl rand -hex 32`. Production publishes the agent on host port **8569** (`8569:8080`). Chroma has no host port. The agent calls `http://chroma-gate:8000`, and the gate forwards authorized requests to `http://chromadb:8000` on a private network named `hermes-prod-chroma-net`. Check production health at `http://127.0.0.1:8569/health`.

Production also starts the official Nous Research image `nousresearch/hermes-agent` as `hermes-gateway`. That container is the web dashboard. It listens on host port **9119**, and its gateway API listens on host port **8642**. State is the named volume `hermes-prod-gateway`, mounted at `/opt/data`. Set `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`, and `HERMES_DASHBOARD_BASIC_AUTH_SECRET` in `docker/env/.env.prod` before expecting the dashboard to accept logins. Gateway model keys belong in gitignored `docker/env/.env.gateway`: `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GOOGLE_API_KEY`, and `COPILOT_GITHUB_TOKEN`. `deploy.sh prod` copies `docker/env/.env.gateway.example` when that file is missing, and `hermes-agent` does not load it. Point Nginx Proxy Manager at `http://<server>:9119`.

Stop a stack with:

```bash
docker compose --env-file docker/env/.env.dev -f docker/docker-compose.dev.yml down
```

## Healthchecks

These URLs run inside each container, against the listen port:

- Agent: `GET http://127.0.0.1:8080/health`
- Chroma: `GET http://127.0.0.1:8000/api/v2/heartbeat`

From the host, development uses ports 8080 and 8000. Production uses port 8569 for the agent. Production Chroma is only reachable through the gate on the Docker network.

`/health` returns HTTP 200 when the process is up. `chroma.reachable` reports whether the heartbeat succeeded. `model.configured` reports whether the provider variables are set. `jev.mode` and `jev.configured` report the System One client. The response omits `CHROMA_AUTH_TOKEN`, `HERMES_API_TOKEN`, `HERMES_MODEL_API_KEY`, and `HERMES_JEV_API_KEY`.

`POST /completions` with `{"prompt":"..."}` sends one chat completion. When `HERMES_API_TOKEN` is set, document, completion, and tool routes require `Authorization: Bearer <HERMES_API_TOKEN>`. Health does not.

## Cursor MCP

`HERMES_MCP_ENABLED` defaults to `off`. Set it to `on` in the agent environment when a Cursor account should call this API. The route is `/mcp` on the agent port: `http://127.0.0.1:8080/mcp` in development and `http://127.0.0.1:8569/mcp` in production. A Cursor cloud agent needs a public `https://` hostname, and that hostname goes in `HERMES_MCP_ALLOWED_HOSTS`. Do not point Cursor at `hermes-gateway` on port 9119 or 8642. For this deployment the public API name is `api.hermes.newplanetit.com.au`. The setup order is [grok-hermes.md](../architecture/grok-hermes.md). `delegate_to_grok` stays off until `HERMES_GROK_HANDOFF` is `ask` or `on`. Those values, including the alias token, belong in `docker/env/.env.agent` on the agent service.

The bearer is `HERMES_API_TOKEN`. Put it in the Cursor user config or the Cursor dashboard, not in git. Headers in that file are literal.

```json
{
  "mcpServers": {
    "hermes": {
      "url": "https://hermes.example/mcp",
      "headers": {
        "Authorization": "Bearer <HERMES_API_TOKEN>"
      }
    }
  }
}
```

Cursor opens this connection. Hermes does not call Cursor, and `complete` still uses `HERMES_MODEL_NAME`. The server allows 60 MCP requests in 60 seconds and then answers 429. The count includes requests that omit the token. `/health` and the other routes are not counted.

## Vector DB

Chroma runs as its own container from `chromadb/chroma:1.0.0` (`CHROMA_IMAGE`). That image is the Rust server. It persists at `/data` and does not include `python` or `curl`. The Compose healthcheck downloads `GET /api/v2/heartbeat` with `/usr/lib/apt/apt-helper`, which is already in the image. The Python client lives in `src/services/chroma.py`. It sends `Authorization: Bearer <token>` when `CHROMA_AUTH_TOKEN` is set. `POST /documents` with `{"id","text"}` upserts into collection `hermes-documents`. `GET /documents/search?q=` returns the nearest documents. The vectors are a local token hash, so shared words rank higher. `chromadb/chroma:1.0.0` does not check tokens, so production runs `chroma-gate` from the same image (`python3 -m services.chroma_gate`) and keeps the database off `hermes-prod-net`.

## Image user

The runtime image creates user `hermes` with uid 10001 and switches to that user before the entrypoint. The build stage runs as root so it can install packages. Every Compose file sets `cap_drop: ALL` on `hermes-agent`. `api.server:serve` checks that the listen port is 1024 or higher and that the memory directory is writable, then the process serves with those capabilities already dropped.

## Build the runtime image

```bash
export GHCR_OWNER=your-github-org
export IMAGE_TAG=0.1.0
docker/scripts/build.sh
```

`build.sh` targets the `runtime` stage. A plain `docker build` without `--target runtime` produces the test stage, which is the last stage in the Dockerfile.
