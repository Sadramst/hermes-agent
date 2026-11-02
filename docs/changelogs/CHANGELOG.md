# Changelog

## [Unreleased]

## [0.4.0] - 2026-10-26

### Added

- [overview.md](../architecture/overview.md) is the top-level map of `hermes-agent`, `chromadb`, `chroma-gate`, and `hermes-gateway`, including the recommended model for each service.
- `hermes-gateway` receives `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GOOGLE_API_KEY` (or `GEMINI_API_KEY`), and `COPILOT_GITHUB_TOKEN` (or `GITHUB_COPILOT_TOKEN`) from gitignored `docker/env/.env.gateway`. `hermes-agent` does not load that file.
- Retrieval-augmented completions. `HERMES_RAG_MODE` (`off` default, `shadow`, `soft`) searches documents with the prompt; soft adds a delimited `## Context` block and returns `sources`. See [021-retrieval.md](../architecture/history/021-retrieval.md).
- Optional embedding provider (`HERMES_EMBED_BASE_URL`, `HERMES_EMBED_MODEL`, `HERMES_EMBED_API_KEY`, `HERMES_EMBED_INPUT_TYPE`) with its own `-v2` collections, and `hermes migrate-documents --from <collection>`.
- `HERMES_MEMORY_INDEX=on` mirrors memory writes into a search index: MCP `search_memory`, `GET /memory/search`, and `hermes reindex-memory`.
- [document-search-policy.md](../architecture/document-search-policy.md) paste block for the gateway `SOUL.md`, and the `mcp_servers.hermes-api` entry (`http://hermes-agent:8080/mcp/`, bearer `${HERMES_API_TOKEN}`) that lives on the gateway volume.
- Frozen retrieval eval in `tests/test_data/retrieval/` and `scripts/eval_retrieval.py` for a live stack.

### Changed

- `POST /documents` chunks text (1500 characters, 200 overlap), accepts an optional `source`, skips re-embedding unchanged text, and returns `chunks` and `unchanged`. The document cap rises from 16000 to 100000 characters.
- Search fetches twice the requested neighbors and fuses a keyword ranking before the `chroma-passage` pack. Matches carry `source_id`, `chunk`, and `source` when stored with chunk metadata, and MCP results start with a `[label]` line.
- `GET /health` adds `retrieval` (mode, embedder name, collections). MCP lists seven tools.
- Production embeddings use OpenRouter `openai/text-embedding-3-small` with `HERMES_EMBED_INPUT_TYPE=off`. Hosted NVIDIA embedding ids `nvidia/llama-nemotron-embed-1b-v2` and `nvidia/llama-3.2-nv-embedqa-1b-v2` return HTTP 410, and `nvidia/nemotron-3.5-embed-1b` returns HTTP 403 unless the key is entitled to it.

## [0.3.10] - 2026-10-21

### Added

- `docker/scripts/cleanup-disk.sh` for safe Docker/apt/journal cleanup on Hermes hosts (default keeps volumes and in-use images).

### Changed

- Soft mode: MCP `list_skills`, `recall`, and `remember` call the agent directly (no soft tool-call hold). Soft memory-write still skips one-shot chatter (`skipped`). HTTP `POST /tools` is unchanged. See `docs/architecture/shared-memory-policy.md` and `docs/superpowers/specs/2026-10-21-mcp-soft-memory-design.md`.
- Production `HERMES_JEV_MODE` is `soft` (`GET /health` → `jev.mode=soft`). `HERMES_MODEL_SMALL` stays unset by choice, so soft completions stay on `HERMES_MODEL_NAME`. Rollback is set mode back to `shadow` and redeploy.
- Production gateway `SOUL.md` includes the skill-line standing instruction from `docs/architecture/gateway-skill-line-policy.md` (`suggest_skill` via MCP `hermes-api`).

## [0.3.9] - 2026-10-21

### Added

- Optional `HERMES_MODEL_SMALL`: in soft mode, when it is set and the model-router returns tier `small` with reason `ok`, the generative call uses that id; otherwise completions stay on `HERMES_MODEL_NAME`. Shadow still logs the tier and never switches. Production remains on `HERMES_JEV_MODE=shadow` until soft promotion.

## [0.3.8] - 2026-10-21

### Fixed

- `GET /health` reports `agent.__version__` instead of a hardcoded `0.1.0`.
- `deploy.sh` unsets shell `IMAGE_TAG` / `GHCR_OWNER` so Compose uses the env file.

## [0.3.7] - 2026-10-21

### Added

- MCP `suggest_skill` returns the advisory skill line for gateway-supplied rosters; completions soft/shadow behaviour is unchanged. Paste `docs/architecture/gateway-skill-line-policy.md` into gateway `SOUL.md` after deploy.
- Recorded the all-frontier model-router comparison artifact at `tests/test_data/router/all-frontier-run.json`; completions still stay on `HERMES_MODEL_NAME` until a later smaller-model PR.

## [0.3.6] - 2026-10-21

### Fixed

- `POST /mcp` no longer answers **307** to `/mcp/`. The app rewrites the bare path in-process so clients that drop `Authorization` on redirects (for example hosted BDK MCP) still authenticate.

## [0.3.5] - 2026-10-21

### Fixed

- `HERMES_GROK_WEBHOOK_URL` accepts Cursor managed alias paths that end in `/v1/channels/hermes/task` (for example `.../engine/v1/channels/hermes/task`). Exact-path-only validation rejected those URLs at startup.

### Added

- `HERMES_GROK_HANDOFF` defaults to `off`. `delegate_to_grok` is on the `POST /tools` allowlist and absent from `/mcp`. `off` refuses the call. `ask` asks a person and does not POST. `on` POSTs `handoffId` and `task` to `HERMES_GROK_WEBHOOK_URL` and returns the id on HTTP 202. Health reports `grok.handoff` and omits the alias token. Production reads the webhook values from `docker/env/.env.agent` on `hermes-agent` only. See `docs/architecture/grok-hermes.md`.
- Plan for Grok and Hermes. `https://hermes.newplanetit.com.au` stays the dashboard on port 9119. Grok calls MCP at `https://api.hermes.newplanetit.com.au/mcp`. A later tool, `delegate_to_grok`, posts one task and returns on HTTP 202. See `docs/architecture/grok-hermes.md`.
- `HERMES_MCP_ENABLED` defaults to `off`. When it is `on`, `/mcp` is a streamable HTTP MCP server Cursor calls with `HERMES_API_TOKEN`. The tools are `list_skills`, `recall`, `remember`, `search_documents`, and `complete`. `delete_memory` is absent. `complete` still uses `HERMES_MODEL_NAME`. Health reports `mcp.enabled` and still omits tokens. Sixty requests in sixty seconds answer 429. See `docs/architecture/cursor-account.md`.
- The plan records two later improvements, neither built yet: a recorded all-frontier run of `tests/test_data/router/tasks.json` before any smaller-model switch, and a `hermes-gateway` hook for the skill-suggestion line.
- Soft mode stops tool calls that follow a looping `supervisor` judgment. The calls that already ran stay as they are. Shadow still logs that judgment and runs the batch. A Jev error still runs the rest of the batch. The completion text stays as the model wrote it. The step limit still runs nothing when the batch is too long.
- Shadow and soft modes log a `supervisor` judgment for a tool batch and for a completion: whether the steps are looping and whether the gathered evidence looks complete. Tool results, the completion text, and the step limit stay unchanged. The model reply and the caller prompt stay out of that judgment. A Jev error still returns the original result. Mode `off` makes no Jev call.
- Shadow and soft completions log a `model-router` tier. A choice of `small` with confidence above the unsure line is logged as `small`. Low confidence, `none`, an unknown choice, and a Jev error log `frontier`. The generative call still uses `HERMES_MODEL_NAME`. An inbound guardrail hold skips the router.
- Soft mode holds a `POST /tools` call unless Jev picked that tool, the need noul is not below the label, the safety noul is above unsure, and the blast score is below the irreversible level. A safety noul at the unsure line asks a person. A Jev error asks a person instead of running. `delete_memory` still asks a person. Shadow still logs the judgment and runs the allowlist.
- Shadow and soft modes log a `tool-call` judgment for `POST /tools`: whether a tool is needed, which allowlisted tool Jev would pick, and a safety score for each call. The allowlist still runs. `delete_memory` still asks a person. A Jev error still runs the batch. Argument values stay out of the questions and the log. Mode `off` makes no Jev call.
- `POST /tools` runs an allowlist in code: `recall`, `remember`, and `list_skills`. A batch past the step limit runs nothing. `delete_memory` asks a person and does not delete. The runner does not call Jev. The route uses `HERMES_API_TOKEN` when that credential is set.
- Soft mode skips a memory write when the `memory-write` judgment is one-shot chatter: a choice of `none`, an unknown kind, or a worth noul below the label. A durable kind is still stored. Shadow still logs that judgment and writes the file. A Jev error still writes. Mode `off` makes no Jev call.
- Shadow mode logs a `memory-write` judgment when a memory record is stored: whether the value looks durable, and a kind of `fact`, `preference`, `procedure`, or none. The file is still written. Mode `off` makes no Jev call.
- Soft mode withholds the model reply when a `guardrails` route is `review` or `block`. An inbound hold skips the model call. A Jev error logs `review` and, in soft mode, withholds the reply. Shadow still logs the route and returns the model text.
- Shadow and soft modes log a `guardrails` route on `POST /completions` for the caller prompt and the model reply: `pass`, `review`, or `block`. An irreversible blast radius logs `block`. Mode `off` makes no Jev call.
- Soft mode returns `chroma-passage` matches whose relevance score reaches the level that says the passage states an answer. Shadow still logs that judgment and returns every neighbor. A Jev error returns every neighbor, so search is not blocked. Mode `off` makes no Jev call.
- Shadow and soft modes log a `chroma-passage` judgment on `GET /documents/search`: one Noul and one relevance Score per match.
- Soft mode (`HERMES_JEV_MODE=soft`) runs the skill-suggestion pack and inserts a `skill_relevance` block between the skill index and the request. The model may ignore it. A Jev error leaves the block out and the generative call still runs.
- Shadow mode (`HERMES_JEV_MODE=shadow`) runs the skill-suggestion pack during `POST /completions` and logs Jev's winner against the skill index. The model prompt stays the skill index plus the caller prompt. Mode `off` makes no Jev call.
- Jev client at `src/services/jev.py` for `POST /v1/systemone`, plus settings, health fields, and decision plumbing. `HERMES_JEV_MODE` defaults to `off`. `GET /health` reports `jev.mode` and `jev.configured` and omits the key.
- `POST /completions` prefixes a loaded skill index onto the caller prompt, then still makes one generative call. Empty skill directories keep a stable wrapper.
- Architecture plan for TypeSafe Jev as a System One decision layer that Hermes calls. Jev does not replace the generative model, the Nous gateway, or tool execution. See `docs/architecture/jev-system-one.md`.

### Fixed

- Completion requests call `OpenerDirector.open()`. Calling the opener object raised `TypeError` and `POST /completions` returned HTTP 500.
- The deploy workflow can render production Compose without the gitignored `docker/env/.env.prod`. The job writes a render-only stand-in. Real tokens stay on the server.
- `deploy.sh` starts `init.sh` with `bash`, so a clone without the executable bit no longer fails with `Permission denied`.
- Chroma 1.0.0 stays healthy: the probe no longer calls `python`, and the data volume is mounted at `/data`.

### Changed

- Production publishes the agent on host port 8569. Chroma is not published. Container listen ports stay 8080 and 8000.

### Added

- `POST /completions` sends one chat completion to an OpenAI-compatible provider. Production requires `HERMES_MODEL_BASE_URL`, `HERMES_MODEL_NAME`, and `HERMES_MODEL_API_KEY`. Development and test may leave them empty.
- `HERMES_API_TOKEN` guards `POST /documents`, `GET /documents/search`, and `POST /completions` when it is set. Production requires it. `GET /health` stays open and still omits secrets.
- The agent container sets `cap_drop: ALL`. Startup checks that the listen port is 1024 or higher and that the memory directory is writable.
- `POST /documents` and `GET /documents/search` save and search one Chroma collection, `hermes-documents`.
- Production requires `CHROMA_AUTH_TOKEN` on the agent and on Chroma. A `chroma-gate` proxy checks the bearer token. Chroma 1.0.0 does not enforce tokens, so the database has no published host port and sits on a network the gateway cannot join.
- Production starts the Nous Research gateway image with the web dashboard on host port 9119 and the gateway API on host port 8642.
- Containerized Hermes Agent with DEV, TEST, and PROD Compose stacks.
- ChromaDB service, shared Docker network, and persistent volumes for memory, skills, and embeddings.
- Multi-stage Ubuntu image that runs as user `hermes` and publishes to GHCR.
- Health endpoint, file memory, skill loader, and the `bootstrap-hermes-stack` skill.
- Unit, contract, and optional Chroma heartbeat tests.
- GitHub Actions workflows for test, image build, GHCR release, and Compose render.
