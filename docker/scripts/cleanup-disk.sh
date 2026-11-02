#!/usr/bin/env bash
# Safe disk cleanup for Hermes hosts (Docker + apt + journal).
# Default: never remove volumes or in-use images. Does not touch LVM.
set -euo pipefail

USAGE='Usage: cleanup-disk.sh [--unused-images] [--volumes] [--dry-run]

  (default)         Stopped containers, dangling images, build cache,
                    apt cache, journal vacuum to 100M. Keeps all tagged
                    images and all volumes.
  --unused-images   Also remove images not used by any container
                    (old hermes-agent tags, dangling layers). Keeps
                    images for currently running containers.
  --volumes         Also prune unused Docker volumes. DANGEROUS: can
                    delete stopped-stack data. Requires typing YES.
  --dry-run         Print planned docker prune commands only; still
                    prints df / docker system df.
'

UNUSED_IMAGES=0
PRUNE_VOLUMES=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --unused-images) UNUSED_IMAGES=1 ;;
    --volumes) PRUNE_VOLUMES=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      printf '%s' "${USAGE}"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      printf '%s' "${USAGE}" >&2
      exit 1
      ;;
  esac
  shift
done

run() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "+ $*"
  else
    "$@"
  fi
}

echo "== before =="
df -h / || true
docker system df 2>/dev/null || true
echo

run docker container prune -f
if [[ "${UNUSED_IMAGES}" -eq 1 ]]; then
  # -a removes unused tagged images; running containers' images stay.
  run docker image prune -af
else
  run docker image prune -f
fi
run docker builder prune -af

if [[ "${PRUNE_VOLUMES}" -eq 1 ]]; then
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "+ docker volume prune -f   # would require YES confirmation when not dry-run"
  else
    echo "About to prune UNUSED Docker volumes (named volumes not attached to a container)."
    echo "This can delete Chroma/memory data if the stack is down. Type YES to continue:"
    read -r confirm
    if [[ "${confirm}" == "YES" ]]; then
      docker volume prune -f
    else
      echo "Skipped volume prune."
    fi
  fi
fi

if [[ "${DRY_RUN}" -eq 0 ]]; then
  if command -v journalctl >/dev/null 2>&1; then
    journalctl --vacuum-size=100M || true
  fi
  if command -v apt-get >/dev/null 2>&1; then
    apt-get clean || true
  fi
else
  echo "+ journalctl --vacuum-size=100M"
  echo "+ apt-get clean"
fi

echo
echo "== after =="
df -h / || true
docker system df 2>/dev/null || true

if [[ "${UNUSED_IMAGES}" -eq 0 ]]; then
  echo
  echo "Tip: re-run with --unused-images to drop old hermes-agent tags not in use."
fi
