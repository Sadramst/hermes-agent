#!/usr/bin/env bash
# Snapshot Hermes named Docker volumes (memory, skills, ChromaDB, gateway) to compressed archives.
# Usage: bash docker/scripts/backup-brain.sh [--dest ./backups] [--keep 7] [--dry-run]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${ROOT}/backups"
KEEP=7
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST="$2"; shift ;;
    --keep) KEEP="$2"; shift ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      echo "Usage: backup-brain.sh [--dest DIR] [--keep N] [--dry-run]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUT_DIR="${DEST}/${STAMP}"
VOLUMES=(hermes-prod-memory hermes-prod-skills hermes-prod-chroma hermes-prod-gateway)

if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "+ mkdir -p ${OUT_DIR}"
  for vol in "${VOLUMES[@]}"; do
    echo "+ snapshot ${vol} -> ${OUT_DIR}/${vol}.tar.gz"
  done
  echo "+ keep latest ${KEEP} backup directories under ${DEST}"
  exit 0
fi

mkdir -p "${OUT_DIR}"
for vol in "${VOLUMES[@]}"; do
  if docker volume inspect "${vol}" >/dev/null 2>&1; then
    docker run --rm \
      -v "${vol}:/source:ro" \
      -v "${OUT_DIR}:/backup" \
      alpine:3.20 \
      tar -czf "/backup/${vol}.tar.gz" -C /source .
    echo "Backed up ${vol} -> ${OUT_DIR}/${vol}.tar.gz"
  else
    echo "Skipping missing volume ${vol}"
  fi
done

# Prune older snapshot folders past KEEP
mapfile -t SNAPS < <(find "${DEST}" -mindepth 1 -maxdepth 1 -type d | sort -r)
if [[ "${#SNAPS[@]}" -gt "${KEEP}" ]]; then
  for old in "${SNAPS[@]:${KEEP}}"; do
    rm -rf "${old}"
    echo "Pruned old backup: ${old}"
  done
fi
