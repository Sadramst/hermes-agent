#!/usr/bin/env bash
# Sync version-controlled gateway templates (`gateway/`) into the running
# `hermes-gateway` container volume (`/opt/data`) with timestamped backups.
# Usage: bash docker/scripts/bootstrap-gateway.sh [--force-user] [--force-config]
set -euo pipefail

FORCE_USER=0
FORCE_CONFIG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-user) FORCE_USER=1 ;;
    --force-config) FORCE_CONFIG=1 ;;
    -h|--help)
      echo "Usage: bootstrap-gateway.sh [--force-user] [--force-config]"
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
ENV_FILE="${ROOT}/docker/env/.env.prod"
GATEWAY_ENV="${ROOT}/docker/env/.env.gateway"
COMPOSE="${ROOT}/docker/docker-compose.prod.yml"
STAMP="$(date -u +%Y%m%d-%H%M%S)"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Copy docker/env/.env.prod.example first." >&2
  exit 1
fi

compose() {
  if [[ -f "${GATEWAY_ENV}" ]]; then
    docker compose --env-file "${ENV_FILE}" --env-file "${GATEWAY_ENV}" -f "${COMPOSE}" "$@"
  else
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE}" "$@"
  fi
}

backup_and_copy() {
  local src="$1"
  local dest="$2"
  local force="$3"
  local exists
  exists="$(compose exec -T hermes-gateway sh -c "test -f '${dest}' && echo yes || echo no")"
  if [[ "${exists}" == "yes" && "${force}" -eq 0 ]]; then
    echo "Keeping existing ${dest} (pass --force-* to overwrite)."
    return 0
  fi
  if [[ "${exists}" == "yes" ]]; then
    compose exec -T hermes-gateway sh -c "cp '${dest}' '${dest}.bak-${STAMP}'"
    echo "Backed up ${dest} -> ${dest}.bak-${STAMP}"
  fi
  compose exec -T hermes-gateway sh -c "mkdir -p /opt/data && cat > '${dest}'" < "${src}"
  echo "Synced ${src} -> ${dest}"
}

# SOUL.md is always synced from git (with backup) so standing policies stay current.
backup_and_copy "${ROOT}/gateway/SOUL.md" "/opt/data/SOUL.md" 1
backup_and_copy "${ROOT}/gateway/USER.md" "/opt/data/USER.md" "${FORCE_USER}"
backup_and_copy "${ROOT}/gateway/config.yaml.example" "/opt/data/config.yaml" "${FORCE_CONFIG}"

echo "Gateway files synced. Restarting hermes-gateway so Telegram/dashboard sessions reload..."
compose restart hermes-gateway

