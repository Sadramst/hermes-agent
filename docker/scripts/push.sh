#!/usr/bin/env bash
set -euo pipefail

: "${GHCR_OWNER:?GHCR_OWNER is required}"
: "${IMAGE_TAG:?IMAGE_TAG is required}"

docker push "ghcr.io/${GHCR_OWNER}/hermes-agent:${IMAGE_TAG}"
