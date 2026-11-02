#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
: "${GHCR_OWNER:?GHCR_OWNER is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

docker build \
  --file "${ROOT}/docker/Dockerfile" \
  --target runtime \
  --tag "ghcr.io/${GHCR_OWNER}/hermes-agent:${IMAGE_TAG}" \
  "${ROOT}"
