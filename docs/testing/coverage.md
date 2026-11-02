# Coverage

The first suite covers the service skeleton and the deployment contract.

## Covered

- Settings defaults for dev, test, and prod, including distinct paths and hosts when overrides are absent
- `GET /health` status, environment, Chroma reachability, and omission of the auth token
- Memory read and write, including rejected path escapes
- Skill loading, including `bootstrap-hermes-stack` version `1.19.0`
- Completion prompts include the skill index (name, version, purpose). Empty skill directories keep a stable wrapper. The assembled prompt still respects `MAX_PROMPT_CHARS`
- Chroma client URL `http://chromadb:8000/api/v2/heartbeat`, bearer header, and v1 fallback
- `POST /documents` and `GET /documents/search` for collection `hermes-documents`
- Production token gate, private Chroma network, and a required `CHROMA_AUTH_TOKEN`
- Model provider settings and one `POST /chat/completions` request, including the bearer key and a rejected redirect
- `HERMES_API_TOKEN` on document and completion routes, with `GET /health` left open
- `cap_drop: ALL` on the agent service and the unprivileged-port startup check
- CLI `health` and `skills`
- Dockerfile stages, non-root user, and healthcheck
- Compose networks, volumes, healthchecks, restart policies, and GHCR image fields
- Production host port 8569 (agent) with Chroma unpublished; development host ports 8080 and 8000
- Presence of architecture diagrams and deployment docs
- Jev System One plan keeps Hermes in control and is listed from `planned.md`
- Jev client request shape, rejected redirects, health fields without the key, mode `off` making no Jev call, compose outcomes from recorded fixtures, and Choice packs that must include `none`
- Shadow skill suggestion: two recorded Jev calls when the gate passes, one when it does not, no call when mode is off or no skills are loaded, the caller prompt stays out of question instructions, and a Jev error still returns the model text
- Soft skill suggestion adds a `skill_relevance` block and keeps the full skill index. A low gate says nothing fits. A Jev error omits the block. Mode off makes no Jev call
- Chroma passage shadow: one recorded Jev call for the returned matches, no call when mode is off or the neighbor list is empty, the query and passage text stay out of question instructions, and a Jev error still returns every match. Soft mode returns passages at the helping relevance level and still returns every match when Jev fails
- Guardrail shadow: one recorded Jev call for the caller prompt and one for the model reply, no call when mode is off, the prompt and reply stay out of question instructions, an irreversible blast radius logs `block` without changing the reply, and a Jev error logs `review` and still returns the model text. Soft mode withholds the reply on review or block, skips the model call on an inbound hold, and withholds the reply when Jev fails
- Memory write gate: one recorded Jev call, no call when mode is off or the key is rejected, and the value stays out of question instructions. Shadow still writes chatter. Soft skips a choice of `none` or a worth noul below the label, and still writes a durable kind. A Jev error still leaves the file in place
- Tool runner: allowlisted calls run in order, an unknown name or an extra argument is refused, `delete_memory` asks a person and leaves the file, a batch past the step limit runs nothing, and mode `off` makes no Jev call. Argument values stay out of the log. `POST /tools` requires `HERMES_API_TOKEN` when it is set
- Tool-call shadow: one recorded Jev call for the batch, no call when mode is off or the batch exceeds the step limit, argument values stay out of question instructions, and a Jev error or a choice of `none` still runs the allowlist. Soft mode runs a picked call only when the safety noul is above unsure and the blast score is below the irreversible level. A Jev error in soft asks a person. `delete_memory` still asks a person
- Model router shadow: one recorded Jev call before the frontier completion, no call when mode is off or an inbound guardrail hold skips the model, the caller prompt stays out of question instructions, low confidence logs `frontier`, and a logged `small` tier still returns `HERMES_MODEL_NAME` unless soft + `HERMES_MODEL_SMALL` + `small`/`ok`. The frozen tasks live in `tests/test_data/router/tasks.json`
- Soft smaller-model switch: unit tests cover soft+small/ok, unset small, shadow no-switch, reason `up`, and JevError fail-closed to frontier
- Frontier router artifact check: `tests/test_data/router/all-frontier-run.json` matches the frozen task tiers (freeze line for gold)
- Gateway skill-line hook: unit tests cover `gateway_skill_line`, plus MCP registration of `suggest_skill`
- Supervisor shadow: one recorded Jev call after a tool batch and after a completion, including a held completion, no call when mode is off, the batch is empty, or the batch exceeds the step limit. Tool output, the caller prompt, and the model reply stay out of the question instructions. A looping judgment and a Jev error still return the original tool results and the original completion text. Soft mode stops calls that follow a looping noul at the unsure line, runs the rest when that noul is below the line or the evidence looks complete, and still runs the rest when Jev fails. A looping completion still returns the model text

## Later

- A running Compose stack in CI
- Line coverage thresholds

The integration heartbeat test is marked `integration` and skips when Chroma is not reachable, so the default CI job stays green on a runner without that service.
