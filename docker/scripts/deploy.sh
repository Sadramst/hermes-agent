#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
case "${ENV_NAME}" in
  dev|test|prod|minipc) ;;
  *)
    echo "Usage: deploy.sh [dev|test|prod|minipc]" >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "${ROOT}/docker/scripts/init.sh"

COMPOSE_ARGS=(-f "${ROOT}/docker/docker-compose.${ENV_NAME}.yml")
ENV_ARGS=(--env-file "${ROOT}/docker/env/.env.${ENV_NAME}")
PROFILE_ARGS=()

if [[ "${ENV_NAME}" == "prod" || "${ENV_NAME}" == "minipc" ]]; then
  GATEWAY_ENV="${ROOT}/docker/env/.env.gateway"
  if [[ ! -f "${GATEWAY_ENV}" ]]; then
    cp "${ROOT}/docker/env/.env.gateway.example" "${GATEWAY_ENV}"
  fi
  chmod 600 "${GATEWAY_ENV}"
  ENV_ARGS=(--env-file "${ROOT}/docker/env/.env.prod" --env-file "${GATEWAY_ENV}")
fi

if [[ "${ENV_NAME}" == "minipc" ]]; then
  MINIPC_ENV="${ROOT}/docker/env/.env.minipc"
  if [[ ! -f "${MINIPC_ENV}" ]]; then
    cp "${ROOT}/docker/env/.env.minipc.example" "${MINIPC_ENV}"
  fi
  chmod 600 "${MINIPC_ENV}"
  mkdir -p "${ROOT}/workspace" "${ROOT}/knowledge" "${ROOT}/backups"
  COMPOSE_ARGS=(-f "${ROOT}/docker/docker-compose.prod.yml" -f "${ROOT}/docker/docker-compose.minipc.yml")
  ENV_ARGS+=(--env-file "${MINIPC_ENV}")
  if grep -Eq '^[[:space:]]*CLOUDFLARE_TUNNEL_TOKEN=[^[:space:]]+' "${MINIPC_ENV}"; then
    PROFILE_ARGS=(--profile tunnel)
  fi
fi

# Shell exports override --env-file for Compose interpolation; always prefer the file.
unset IMAGE_TAG GHCR_OWNER

compose() {
  docker compose "${ENV_ARGS[@]}" "${COMPOSE_ARGS[@]}" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} "$@"
}

if [[ "${ENV_NAME}" == "test" ]]; then
  compose up --build --abort-on-container-exit --exit-code-from hermes-tests
elif [[ "${ENV_NAME}" == "prod" ]]; then
  compose pull
  compose up -d
elif [[ "${ENV_NAME}" == "minipc" ]]; then
  compose up --build -d
else
  compose up --build -d
fi
