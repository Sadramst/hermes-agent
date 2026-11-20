#!/usr/bin/env bash
# Index /knowledge vault (and optional /workspace projects) + memory files into ChromaDB.
# Usage: bash docker/scripts/sync-brain.sh [--projects] [--include-code]
set -euo pipefail

INDEX_PROJECTS=0
INCLUDE_CODE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --projects) INDEX_PROJECTS=1 ;;
    --include-code) INCLUDE_CODE=1 ;;
    -h|--help)
      echo "Usage: sync-brain.sh [--projects] [--include-code]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROD_ENV="${ROOT}/docker/env/.env.prod"
GATEWAY_ENV="${ROOT}/docker/env/.env.gateway"
MINIPC_ENV="${ROOT}/docker/env/.env.minipc"

COMPOSE_CMD=(docker compose --env-file "${PROD_ENV}")
[[ -f "${GATEWAY_ENV}" ]] && COMPOSE_CMD+=(--env-file "${GATEWAY_ENV}")
[[ -f "${MINIPC_ENV}" ]] && COMPOSE_CMD+=(--env-file "${MINIPC_ENV}")
COMPOSE_CMD+=(-f "${ROOT}/docker/docker-compose.prod.yml" -f "${ROOT}/docker/docker-compose.minipc.yml")

CODE_FLAG=()
[[ "${INCLUDE_CODE}" -eq 1 ]] && CODE_FLAG+=(--include-code)

echo "Syncing /knowledge vault..."
"${COMPOSE_CMD[@]}" exec -T hermes-agent hermes ingest /knowledge --prefix brain ${CODE_FLAG[@]+"${CODE_FLAG[@]}"} || true

if [[ "${INDEX_PROJECTS}" -eq 1 ]]; then
  echo "Syncing /workspace projects..."
  "${COMPOSE_CMD[@]}" exec -T hermes-agent hermes ingest /workspace --prefix proj ${CODE_FLAG[@]+"${CODE_FLAG[@]}"} || true
fi

echo "Reindexing memory collection (if HERMES_MEMORY_INDEX=on)..."
"${COMPOSE_CMD[@]}" exec -T hermes-agent hermes reindex-memory || true
