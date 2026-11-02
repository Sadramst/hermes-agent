# Test strategy

Tests are written to lock the stack contract before the containers are treated as done.

## Layers

| Layer | Path | Needs Docker | What it proves |
| --- | --- | --- | --- |
| Unit | `tests/unit/` | No | Settings, health JSON, memory paths, skill loading, Chroma URL, CLI |
| Integration | `tests/integration/` | A reachable Chroma | Live heartbeat. The test skips when nothing answers. |
| Contract | `tests/e2e/` | No | Compose services, mounts, network, Dockerfile user, docs, Mermaid files |

Run the default suite from the repository root:

```bash
python -m pip install -e ".[dev]"
pytest -q -m "not integration"
```

`ci-cd/scripts/verify.sh` runs that command and checks shell script syntax.

The test Compose file runs the same pytest selection inside `hermes-tests` after the agent and Chroma healthchecks pass:

```bash
docker/scripts/deploy.sh test
```

## Failure modes covered

- Missing `HERMES_ENV` or `CHROMA_HOST` raises `SettingsError`.
- Memory keys that leave the storage directory are rejected.
- Broken skill front matter raises `ValueError` and is logged.
- Compose files must keep both services, `hermes-net`, healthchecks, and the three storage mount targets.
- The runtime image stage must be Ubuntu, multi-stage, and switch to user `hermes`.
- The prod image reference must be a `ghcr.io` name with required owner and tag variables.
- Production settings reject a missing model provider or a missing `HERMES_API_TOKEN`.
- Document, completion, and tool routes reject a missing or wrong bearer token when `HERMES_API_TOKEN` is set.
- Completions prefix a skill index onto the caller prompt. An assembled prompt over `MAX_PROMPT_CHARS` is HTTP 400 and does not call the provider.
- `HERMES_JEV_MODE` defaults to `off`. Shadow and soft require a long `HERMES_JEV_API_KEY`. Aliases `jev-latest` and `jev-preview` are rejected. Mode `off` makes no Jev call. Shadow logs a skill suggestion and leaves the completion prompt unchanged. Soft mode adds a `skill_relevance` block the model may ignore. Search in shadow logs a passage judgment and still returns every Chroma neighbor. Soft search returns passages at the helping relevance level. A Jev error still returns every neighbor. Shadow completions log a guardrail route and still return the model text. Soft completions withhold that text on review or block. A guardrail error logs `review`. Shadow memory writes log a kind and still store the record. Soft skips one-shot chatter. A Jev error still stores the record. `POST /tools` runs an allowlist and asks a person before `delete_memory`. Shadow logs a `tool-call` judgment and still runs that allowlist. Soft holds a call unless Jev picked it and the score is clear. A Jev error in soft asks a person instead of running. Shadow and soft log a `model-router` tier and still call the frontier model named by `HERMES_MODEL_NAME`. Shadow logs a `supervisor` judgment and still returns the same tool results and the same completion text. Soft stops tool calls that follow a looping judgment and still returns the completion text. Health omits the Jev key.
- The startup check rejects a listen port below 1024, which would need a capability the agent container drops.
