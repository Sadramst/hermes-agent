#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
case "${ENV_NAME}" in
  dev|test|prod) ;;
  *)
    echo "Usage: deploy.sh [dev|test|prod]" >&2
    exit 1
    ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "${ROOT}/docker/scripts/init.sh"

COMPOSE="${ROOT}/docker/docker-compose.${ENV_NAME}.yml"
ENV_FILE="${ROOT}/docker/env/.env.${ENV_NAME}"

if [[ "${ENV_NAME}" == "prod" ]]; then
  GATEWAY_ENV="${ROOT}/docker/env/.env.gateway"
  if [[ ! -f "${GATEWAY_ENV}" ]]; then
    cp "${ROOT}/docker/env/.env.gateway.example" "${GATEWAY_ENV}"
  fi
  chmod 600 "${GATEWAY_ENV}"
fi

# Shell exports override --env-file for Compose interpolation; always prefer the file.
unset IMAGE_TAG GHCR_OWNER

compose() {
  if [[ "${ENV_NAME}" == "prod" ]]; then
    docker compose --env-file "${ENV_FILE}" --env-file "${ROOT}/docker/env/.env.gateway" -f "${COMPOSE}" "$@"
  else
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE}" "$@"
  fi
}

if [[ "${ENV_NAME}" == "test" ]]; then
  compose up --build --abort-on-container-exit --exit-code-from hermes-tests
elif [[ "${ENV_NAME}" == "prod" ]]; then
  compose pull
  compose up -d
else
  compose up --build -d
fi
