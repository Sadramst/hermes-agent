# Release hygiene (health version + deploy IMAGE_TAG)

**Status:** approved design  
**Date:** 2026-10-21  
**Order:** Track 1 of follow-ups (before model switch and soft promotion)  
**Ship as:** one PR, then tag **v0.3.8** (v0.3.7 already shipped with wrong health version)

## Goal

1. `GET /health` → `version` matches the release semver (same number as the git/GHCR tag without the `v` prefix).
2. `docker/scripts/deploy.sh` always honors `IMAGE_TAG` / `GHCR_OWNER` from the Compose `--env-file`, not a stale shell export.

## Non-goals

- Reporting image digest or a separate `image` health field
- Changing Compose service definitions beyond what deploy already does
- Model switch or soft promotion

## C — health version

**Problem:** `src/agent/__init__.py` has `__version__ = "0.1.0"`, and `_health_payload` in `src/agent/core.py` **hardcodes** `"version": "0.1.0"` instead of importing `__version__`. FastAPI’s app `version=` already uses `__version__`, so OpenAPI and health disagree with the real tag.

**Fix:**

1. Set `__version__ = "0.3.8"` for the next release (or whatever tag this PR ships under).
2. Change `_health_payload` to use `from agent import __version__` (or pass it in) so health cannot drift from the package constant again.
3. Unit test: health payload (or `/health` via TestClient) asserts `version == __version__`.
4. Release checklist: when cutting `vX.Y.Z`, bump `__version__` to `X.Y.Z` in the same changelog commit (document in CHANGELOG or one line in `docs/deployment/docker.md`).

## D — deploy.sh IMAGE_TAG

**Problem:** Compose interpolates `${IMAGE_TAG}` from the **process environment** before the `--env-file`. An exported `IMAGE_TAG=v0.3.6` after `set -a; source …` overrides `.env.prod` and silently redeploys the wrong image.

**Fix:** Near the top of the compose invocation path in `deploy.sh` (before `docker compose … pull` / `up`), run:

```bash
unset IMAGE_TAG GHCR_OWNER
```

so interpolation uses only the env file. Optional one-sentence note in `docs/deployment/docker.md` (not required).

## Success

- After deploy of the tagged image, `curl …/health` shows `"version":"0.3.8"` (matching the tag).
- With a stale `export IMAGE_TAG=v0.3.6` in the shell, `deploy.sh prod` still pulls the tag from `.env.prod`.

## Decisions

- Version source: single `__version__` string, bumped on release (not env-driven).
- Deploy fix: `unset` in `deploy.sh` (not docs-only).
