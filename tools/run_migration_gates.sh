#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PARENT_DIR="$(cd "${ROOT_DIR}/.." && pwd)"
PYTHON="${ROOT_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON}" ]]; then
  echo "[gate] python not found: ${PYTHON}" >&2
  exit 2
fi

echo "[gate] 1/4 check legacy imports"
"${PYTHON}" "${ROOT_DIR}/tools/check_no_legacy_imports.py"

echo "[gate] 2/4 check plugin manifest payload input coverage"
PYTHONPATH="${PARENT_DIR}" "${PYTHON}" "${ROOT_DIR}/tools/check_plugin_manifest_inputs.py"

echo "[gate] 3/4 run tests"
PYTHONPATH="${PARENT_DIR}" "${PYTHON}" -m pytest "${ROOT_DIR}/tests" -q

echo "[gate] 4/4 startup + health (RPC disabled)"
LOG_FILE="/tmp/new_migration_gate_uvicorn.log"
MYT_NEW_ROOT="${ROOT_DIR}" MYT_ENABLE_RPC=0 PYTHONPATH="${PARENT_DIR}" \
  "${PYTHON}" -m uvicorn new.api.server:app --host 127.0.0.1 --port 8001 >"${LOG_FILE}" 2>&1 &
UVICORN_PID=$!
trap 'kill ${UVICORN_PID} >/dev/null 2>&1 || true' EXIT

OK=0
for _ in {1..10}; do
  sleep 1
  if curl -sS "http://127.0.0.1:8001/health" >/tmp/new_migration_gate_health.json 2>/tmp/new_migration_gate_health.err; then
    OK=1
    break
  fi
done

if [[ "${OK}" -ne 1 ]]; then
  cat /tmp/new_migration_gate_health.err >&2 || true
  exit 3
fi

cat /tmp/new_migration_gate_health.json
echo "[gate] PASS"
