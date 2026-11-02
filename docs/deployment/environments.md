# Environments

DEV, TEST, and PROD share the agent and Chroma services. They differ in image source, storage, ports, and restart policy.

| | DEV | TEST | PROD |
| --- | --- | --- | --- |
| Compose file | `docker/docker-compose.dev.yml` | `docker/docker-compose.test.yml` | `docker/docker-compose.prod.yml` |
| Env file | `docker/env/.env.dev` | `docker/env/.env.test` | `docker/env/.env.prod` |
| Agent image | Local build, tag `ghcr.io/${GHCR_OWNER:-local}/hermes-agent:${IMAGE_TAG:-dev}` | Same pattern with the `test` tag | `ghcr.io/${GHCR_OWNER}/hermes-agent:${IMAGE_TAG}` |
| Source | Bind-mounted with uvicorn reload | Installed in the image | Installed in the image |
| Memory and skills | Host bind mounts | tmpfs | Named volumes |
| Embeddings | Named volume | tmpfs | Named volume |
| Published ports | Agent 8080, Chroma 8000 | None | Agent 8569, gateway 8642, dashboard 9119. Chroma is not published |
| Restart | `unless-stopped` | `no` | `unless-stopped` |
| Extra service | None | `hermes-tests` runs pytest | None |

`deploy.sh` passes `--env-file`, which supplies Compose interpolation and the container `env_file` supplies the process environment.

## Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `HERMES_ENV` | Yes | `dev`, `test`, or `prod`. Selects default storage paths when directory variables are omitted. |
| `CHROMA_HOST` | Yes | Chroma hostname. Compose sets `chromadb`. |
| `CHROMA_PORT` | No | Listen port on the Docker network. Default `8000`. Development publishes it on the host as `8000`. Production does not publish it. |
| `CHROMA_AUTH_TOKEN` | Production | Bearer token of at least 16 characters. Production Compose refuses to start when it is missing. Development and test may leave it empty. The health response never includes it. |
| `HERMES_API_TOKEN` | Production | Bearer token of at least 16 characters for `POST /documents`, `GET /documents/search`, `GET /memory/search`, `POST /completions`, and `POST /tools`. `GET /health` does not require it. Development and test may leave it empty, which leaves those routes open. |
| `HERMES_MODEL_BASE_URL` | Production | Provider origin, such as `https://api.example/v1`. The client posts to `{base}/chat/completions` and does not follow redirects. Set together with the model name and key. |
| `HERMES_MODEL_NAME` | Production | Frontier model id sent in the completion request. Letters, digits, and `._:/-`. |
| `HERMES_MODEL_SMALL` | No | Optional smaller completion model id. Used only when `HERMES_JEV_MODE=soft` and the model-router returns `small`/`ok`. Empty keeps soft on `HERMES_MODEL_NAME`. Same base URL and API key as the frontier model. |
| `HERMES_MODEL_API_KEY` | Production | Bearer key for the model provider. At least 16 characters, no whitespace. The health response never includes it. |
| `HERMES_MEMORY_DIR` | No | Default depends on `HERMES_ENV`. Compose sets `/app/storage/memory`. |
| `HERMES_SKILLS_DIR` | No | Default depends on `HERMES_ENV`. Compose sets `/app/storage/skills`. |
| `HERMES_HOST` | No | Bind address. Default `0.0.0.0`. |
| `HERMES_PORT` | No | Listen port inside the agent container. Default `8080`. Production publishes that port on the host as `8569`. Development publishes it as `8080`. |
| `HERMES_LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |
| `HERMES_JEV_MODE` | No | `off` (default), `shadow`, or `soft`. `off` makes no Jev call. `shadow` calls the skill-suggestion pack and logs the winner without changing the completion prompt. `soft` calls the same pack and adds a `skill_relevance` block the model may ignore. Both modes also log a `chroma-passage` judgment on search. Shadow returns every Chroma neighbor. Soft returns passages whose relevance score reaches the helping level. A Jev error returns every neighbor. Shadow completions log a `guardrails` route and still return the model text. Soft completions withhold that text on `review` or `block`. A Jev error on that pack logs `review`. Shadow memory writes log a `memory-write` judgment and still store the record. Soft skips one-shot chatter. A Jev error still stores the record. `shadow` and `soft` require `HERMES_JEV_API_KEY`. |
| `HERMES_JEV_API_KEY` | When mode is not `off` | Bearer key for TypeSafe. At least 16 characters, no whitespace. The health response never includes it. Production may leave Jev off. |
| `HERMES_JEV_BASE_URL` | No | Default `https://api.typesafe.ai/v1`. The client posts to `{base}/systemone` and does not follow redirects. |
| `HERMES_JEV_MODEL` | No | Pinned model id. Default `jev-1.13.0`. `jev-latest` and `jev-preview` are rejected. |
| `HERMES_MCP_ENABLED` | No | `off` (default) or `on`. `off` makes `/mcp` answer 404. `on` serves streamable HTTP MCP at `/mcp` and requires `HERMES_API_TOKEN`, including in development. |
| `HERMES_MCP_ALLOWED_HOSTS` | No | Comma-separated public hostnames, such as `hermes.example`. Localhost is already allowed. A hostname that is not listed is refused. |
| `HERMES_GROK_HANDOFF` | No | `off` (default), `ask`, or `on`. `off` refuses `delegate_to_grok`. `ask` asks a person and does not POST. `on` requires the webhook URL, alias token, and handoff secret, then POSTs one task and returns the id on HTTP 202. |
| `HERMES_GROK_WEBHOOK_URL` | When handoff is `on` | `https` URL ending in `/v1/channels/hermes/task`. The client does not follow redirects. |
| `HERMES_GROK_ALIAS_TOKEN` | When handoff is `on` | Value for `X-Agent-Alias-Token`. At least 16 characters, no whitespace. The health response never includes it. |
| `HERMES_GROK_HANDOFF_SECRET` | When handoff is `on` | Value for `X-Hermes-Handoff`. At least 16 characters, no whitespace. The health response never includes it. |
| `HERMES_EMBED_BASE_URL` | No | Embedding provider origin, such as `https://integrate.api.nvidia.com/v1` or `https://openrouter.ai/api/v1`. The client posts to `{base}/embeddings` and does not follow redirects. Set together with the model and key. Unset keeps the built-in hash vectors. |
| `HERMES_EMBED_MODEL` | With the base URL | Embedding model id. Letters, digits, and `._:/-`. Health reports it. |
| `HERMES_EMBED_API_KEY` | With the base URL | Bearer key for the embedding provider. At least 16 characters, no whitespace. A local server that needs no key still takes a 16-character placeholder. The health response never includes it. |
| `HERMES_EMBED_INPUT_TYPE` | No | `off` (default) or `on`. `on` sends `input_type` `query` or `passage`, which NVIDIA retrieval models require. Leave it `off` for OpenRouter. Hosted NVIDIA ids `nvidia/llama-nemotron-embed-1b-v2` and `nvidia/llama-3.2-nv-embedqa-1b-v2` return HTTP 410, and `nvidia/nemotron-3.5-embed-1b` returns HTTP 403 unless the key is entitled to it. |
| `HERMES_DOCUMENTS_COLLECTION` | No | Document collection. Default `hermes-documents` with hash vectors and `hermes-documents-v2` with a provider. Change it when you change the embedding model, then run `hermes migrate-documents --from <old>`. |
| `HERMES_MEMORY_COLLECTION` | No | Memory index collection. Default `hermes-memory` with hash vectors and `hermes-memory-v2` with a provider. Must differ from the document collection. |
| `HERMES_RAG_MODE` | No | `off` (default), `shadow`, or `soft`. `off` makes no search on a completion. `shadow` searches with the prompt and logs the passage labels. `soft` adds a `## Context` block and returns the labels as `sources` on `POST /completions`. |
| `HERMES_MEMORY_INDEX` | No | `off` (default) or `on`. `on` mirrors kept memory writes into the memory collection so `search_memory` and `GET /memory/search` work. Run `hermes reindex-memory` once after turning it on. |
| `GHCR_OWNER` | Prod image | GitHub user or org for `ghcr.io`. |
| `IMAGE_TAG` | Prod image | Tag pushed and pulled for the agent image. |
| `CHROMA_IMAGE` | No | Default `chromadb/chroma:1.0.0`. |
| `OPENROUTER_API_KEY` | No | OpenRouter key for the Nous gateway. Set it in gitignored `docker/env/.env.gateway`. |
| `NVIDIA_API_KEY` | No | NVIDIA NIM key (`build.nvidia.com`) for the Nous gateway. Same file. |
| `GOOGLE_API_KEY` | No | Google AI Studio key for the Nous gateway `gemini` provider. `GEMINI_API_KEY` fills this when `GOOGLE_API_KEY` is empty. |
| `COPILOT_GITHUB_TOKEN` | No | GitHub token for the Nous gateway `copilot` provider. `gho_`, `github_pat_`, or `ghu_`. A classic `ghp_` token is refused. `GITHUB_COPILOT_TOKEN` fills this when `COPILOT_GITHUB_TOKEN` is empty. |

`docker/env/.env.dev` and `docker/env/.env.test` are checked-in templates. `docker/env/.env.prod` is gitignored, so production owner, tag, and token stay on the server. Copy the dev template shape when creating it. Store extra tokens in an untracked `docker/env/*.local` or `.env.local` file. Grok webhook values belong in gitignored `docker/env/.env.agent`, copied from `docker/env/.env.agent.example`. Production Compose loads that file on `hermes-agent` only. Gateway provider keys belong in gitignored `docker/env/.env.gateway`, copied from `docker/env/.env.gateway.example`. `deploy.sh prod` passes that file for interpolation and loads it on `hermes-gateway` only.

When directory variables are omitted, the process defaults are:

- dev: `storage/memory` and `storage/skills`
- test: `/tmp/hermes-test/memory` and `/tmp/hermes-test/skills`
- prod: `/app/storage/memory` and `/app/storage/skills`
