#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
LOCK_FILE="${ARANET_LOCK_FILE:-/tmp/api_aranet_incremental.lock}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi

cd "${PROJECT_DIR}"
exec /usr/bin/flock -n -E 0 "${LOCK_FILE}" "${PYTHON_BIN}" main.py sync-incremental
