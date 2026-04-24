#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

resolve_service_path() {
  local raw_path="$1"
  if [[ "${raw_path}" = /* ]]; then
    printf '%s\n' "${raw_path}"
  else
    printf '%s\n' "${SERVICE_ROOT}/${raw_path}"
  fi
}

resolve_exec_or_path() {
  local raw_value="$1"
  if [[ "${raw_value}" == */* ]]; then
    resolve_service_path "${raw_value}"
  else
    printf '%s\n' "${raw_value}"
  fi
}

command_exists() {
  local raw_value="$1"
  if [[ "${raw_value}" == */* ]]; then
    [[ -x "${raw_value}" ]]
  else
    command -v "${raw_value}" >/dev/null 2>&1
  fi
}

if [[ -f "${SERVICE_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SERVICE_ROOT}/.env"
  set +a
fi

CONFIGURED_PYTHON="$(resolve_exec_or_path "${WAN_PYTHON_BIN:-.venv/bin/python}")"
REPORT_PYTHON="${WAN_CHECK_PYTHON_BIN:-}"

if [[ -z "${REPORT_PYTHON}" ]]; then
  if command_exists "${CONFIGURED_PYTHON}"; then
    REPORT_PYTHON="${CONFIGURED_PYTHON}"
  elif command -v python3 >/dev/null 2>&1; then
    REPORT_PYTHON="python3"
  else
    echo "[error] No usable Python interpreter was found for environment checks." >&2
    exit 1
  fi
fi

cd "${SERVICE_ROOT}"
PYTHONPATH="${SERVICE_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  "${REPORT_PYTHON}" -m app.env_report "$@"
