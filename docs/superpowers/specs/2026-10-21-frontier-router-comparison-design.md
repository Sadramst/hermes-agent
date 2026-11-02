# Frontier router comparison (recorded run)

**Status:** approved design  
**Date:** 2026-10-21  
**Roadmap:** shared-knowledge #4 (comparison only; no model switch)  
**Parent:** [jev-system-one.md](../../architecture/jev-system-one.md) § model router; frozen set [tasks.json](../../../tests/test_data/router/tasks.json)

## Goal

Prove, with a committed artifact, that the live `model-router` pack labels the frozen tasks the same way the gold file does:

| Task id | Gold tier |
| --- | --- |
| `plan` | `frontier` |
| `easy` | `small` |

Completions stay on `HERMES_MODEL_NAME`. This work does **not** select a smaller model.

## Non-goals

- Adding `HERMES_MODEL_SMALL` or changing `HermesAgent.complete()` to switch models
- Soft-mode threshold changes
- Calling `POST /completions` as part of the recording
- Live TypeSafe calls in default CI

## Approach

One opt-in recorder script (live Jev) plus an offline CI/unit check of the committed result file.

## Recorder

- **Path:** `scripts/record_frontier_router_run.py` (or equivalent under `scripts/`)
- **Reads:** `tests/test_data/router/tasks.json`
- **Calls:** existing `agent.decisions.model_router.judge` with a real Jev client (same settings shape as Hermes: `HERMES_JEV_API_KEY`, optional `HERMES_JEV_BASE_URL` / `HERMES_JEV_MODEL`)
- **Does not:** invoke the generative model or change production env
- **Writes:** `tests/test_data/router/all-frontier-run.json`
- **Skip:** exit non-zero with a clear message if `HERMES_JEV_API_KEY` is missing (do not invent fixtures)

### Artifact shape

```json
{
  "note": "All-frontier router comparison. Completions were not switched to a smaller model.",
  "recorded_at": "<ISO-8601 UTC>",
  "jev_model": "<id from Jev responses>",
  "tasks": [
    {
      "id": "plan",
      "prompt": "<from tasks.json>",
      "gold_tier": "frontier",
      "logged_tier": "frontier",
      "reason": "<from label_tier>",
      "confidence": null,
      "match": true
    }
  ]
}
```

- `confidence` is optional/null when not applicable (e.g. frontier/`none` paths).
- `match` is `logged_tier == gold_tier`.
- The recorder may write the file even if some tasks mismatch; CI fails until all `match` are true (or the offline test asserts equality directly).

## Offline verification

- Default pytest (no integration mark / no API key) loads `tasks.json` and `all-frontier-run.json`.
- Asserts: every task id in `tasks.json` appears once in the run file; for each, `logged_tier == gold_tier` (and equals the gold `tier` from `tasks.json`).
- Missing or stale coverage (task id in gold but absent from run) fails the test.

## Pass rule

For every task in `tasks.json`, the **logged router tier** equals the gold `tier`. Confidence and reason are recorded for audit only; they do not fail CI unless the tier mismatches.

## Later (out of this design)

A separate PR may introduce a smaller completion model **only after** this artifact is green. Low router confidence continues to default **up** to frontier.

## Tests

| Layer | What |
| --- | --- |
| Unit / contract (CI) | Artifact matches gold tiers; covers all task ids |
| Live (opt-in, not CI) | Run the recorder with a real key to refresh the artifact |

## Pointers

- Pack: `src/agent/decisions/model_router.py`
- Frozen prompts: `tests/test_data/router/tasks.json`
- Roadmap: [2026-10-21-shared-knowledge-roadmap.md](2026-10-21-shared-knowledge-roadmap.md)
