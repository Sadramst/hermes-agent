#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python -m pytest -q -m "not integration"
for script in docker/scripts/*.sh ci-cd/scripts/*.sh; do
  bash -n "${script}"
done
