#!/usr/bin/env bash
set -euo pipefail

REPORT_TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
OPENCLAW_CMD=(node /app/openclaw.mjs)

echo "[self-maintenance] started at ${REPORT_TS}"

run_step() {
  local label="$1"
  shift
  echo "--- ${label}"
  if "$@"; then
    echo "OK: ${label}"
    return 0
  else
    local code=$?
    echo "ERROR: ${label} failed (exit ${code})"
    return ${code}
  fi
}

run_optional_step() {
  local label="$1"
  shift
  echo "--- ${label}"
  if "$@"; then
    echo "OK: ${label}"
  else
    local code=$?
    echo "WARN: ${label} failed (exit ${code}) — continuing (container/non-systemd likely)."
  fi
}

if [[ ! -f "/app/openclaw.mjs" ]]; then
  echo "ERROR: /app/openclaw.mjs not found; cannot perform automated update."
  exit 2
fi

run_step "OpenClaw update status (pre)" "${OPENCLAW_CMD[@]}" update status
run_step "OpenClaw update (non-interactive)" "${OPENCLAW_CMD[@]}" update --yes
run_optional_step "OpenClaw gateway restart" "${OPENCLAW_CMD[@]}" gateway restart
run_optional_step "OpenClaw gateway status" "${OPENCLAW_CMD[@]}" gateway status
run_step "OpenClaw update status (post)" "${OPENCLAW_CMD[@]}" update status

echo "[self-maintenance] completed"
