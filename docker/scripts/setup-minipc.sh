#!/usr/bin/env bash
# Idempotent first-time & repeat setup for Sadra's Mini PC Home Brain host.
# Usage: bash docker/scripts/setup-minipc.sh [--no-start] [--dry-run]
set -euo pipefail

NO_START=0
DRY_RUN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start) NO_START=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: setup-minipc.sh [--no-start] [--dry-run]"
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

run_or_echo() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "+ $*"
  else
    "$@"
  fi
}

command -v docker >/dev/null 2>&1 || { echo "Docker is not installed." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 plugin is required." >&2; exit 1; }

if [[ "${DRY_RUN}" -eq 0 ]]; then
  [[ -f "${PROD_ENV}" ]] || cp "${ROOT}/docker/env/.env.prod.example" "${PROD_ENV}"
  [[ -f "${GATEWAY_ENV}" ]] || cp "${ROOT}/docker/env/.env.gateway.example" "${GATEWAY_ENV}"
  [[ -f "${MINIPC_ENV}" ]] || cp "${ROOT}/docker/env/.env.minipc.example" "${MINIPC_ENV}"
  chmod 600 "${PROD_ENV}" "${GATEWAY_ENV}" "${MINIPC_ENV}"
else
  echo "+ ensure .env.prod, .env.gateway, .env.minipc exist with chmod 600"
fi

generate_token() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    python3 -c "import secrets; print(secrets.token_hex(32))"
  fi
}

replace_placeholder() {
  local file="$1"
  local key="$2"
  local value="$3"
  if [[ -f "${file}" ]] && grep -Eq "^${key}=replace-with-" "${file}"; then
    python3 -c "
from pathlib import Path
import re, sys
p = Path(sys.argv[1])
text = p.read_text(encoding='utf-8')
p.write_text(re.sub(r'^' + re.escape(sys.argv[2]) + r'=.*$', sys.argv[2] + '=' + sys.argv[3], text, flags=re.MULTILINE), encoding='utf-8')
" "${file}" "${key}" "${value}"
    echo "Generated random ${key} in ${file}"
  fi
}

if [[ "${DRY_RUN}" -eq 0 ]]; then
  replace_placeholder "${PROD_ENV}" "CHROMA_AUTH_TOKEN" "$(generate_token)"
  replace_placeholder "${PROD_ENV}" "HERMES_API_TOKEN" "$(generate_token)"
  replace_placeholder "${PROD_ENV}" "HERMES_DASHBOARD_BASIC_AUTH_SECRET" "$(generate_token)"
fi

resolve_host_dir() {
  local var_name="$1"
  local fallback="$2"
  local raw=""
  if [[ -f "${MINIPC_ENV}" ]]; then
    raw="$(grep -E "^${var_name}=" "${MINIPC_ENV}" | tail -n1 | cut -d= -f2- || true)"
  fi
  raw="${raw:-${fallback}}"
  if [[ "${raw}" == /* ]]; then
    echo "${raw}"
  else
    # Compose resolves relative bind mounts against docker/
    python3 -c "from pathlib import Path; import sys; print((Path(sys.argv[1]) / sys.argv[2]).resolve())" "${ROOT}/docker" "${raw}"
  fi
}

PROJECTS_HOST="$(resolve_host_dir HERMES_HOST_PROJECTS_DIR ../workspace)"
KNOWLEDGE_HOST="$(resolve_host_dir HERMES_HOST_KNOWLEDGE_DIR ../knowledge)"

run_or_echo mkdir -p "${PROJECTS_HOST}" "${KNOWLEDGE_HOST}" "${ROOT}/backups"

# Ensure non-root container user (uid=10001) can read/write host workspace projects seamlessly.
if command -v setfacl >/dev/null 2>&1; then
  run_or_echo setfacl -m u:10001:rwx -d -m u:10001:rwx "${PROJECTS_HOST}" || true
  run_or_echo setfacl -m u:10001:rx -d -m u:10001:rx "${KNOWLEDGE_HOST}" || true
fi

MISSING_KEYS=0
if [[ -f "${PROD_ENV}" ]] && grep -Eq '^HERMES_MODEL_API_KEY=replace-with-' "${PROD_ENV}"; then
  echo "ACTION NEEDED: Set HERMES_MODEL_API_KEY (and optional HERMES_EMBED_API_KEY) in ${PROD_ENV}"
  MISSING_KEYS=1
fi
if [[ -f "${GATEWAY_ENV}" ]] && ! grep -Eq '^[[:space:]]*TELEGRAM_BOT_TOKEN=[^[:space:]]+' "${GATEWAY_ENV}"; then
  echo "INFO: TELEGRAM_BOT_TOKEN is not uncommented in ${GATEWAY_ENV} (ok if configured in /opt/data/.env)."
fi

if [[ "${NO_START}" -eq 1 || "${DRY_RUN}" -eq 1 || "${MISSING_KEYS}" -eq 1 ]]; then
  echo "Pre-flight complete. Once keys are filled in, run:"
  echo "  bash docker/scripts/deploy.sh minipc"
  echo "  bash docker/scripts/bootstrap-gateway.sh --force-config"
  exit 0
fi

bash "${ROOT}/docker/scripts/deploy.sh" minipc
bash "${ROOT}/docker/scripts/bootstrap-gateway.sh" --force-config

echo "Waiting briefly for API health..."
sleep 5
curl -fsS http://127.0.0.1:8569/health && echo
docker compose --env-file "${PROD_ENV}" --env-file "${GATEWAY_ENV}" --env-file "${MINIPC_ENV}" \
  -f "${ROOT}/docker/docker-compose.prod.yml" -f "${ROOT}/docker/docker-compose.minipc.yml" \
  exec -T hermes-gateway hermes mcp test hermes-api || true
