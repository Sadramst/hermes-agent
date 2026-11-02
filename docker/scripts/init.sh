#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
mkdir -p "${ROOT}/storage/memory" "${ROOT}/storage/skills"
echo "Initialized storage directories under ${ROOT}/storage"
