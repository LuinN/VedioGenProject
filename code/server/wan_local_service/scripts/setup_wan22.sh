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

if [[ -f "${SERVICE_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SERVICE_ROOT}/.env"
  set +a
fi

PYTHON_BOOTSTRAP_BIN="$(resolve_exec_or_path "${WAN_PYTHON_SETUP_BIN:-${WAN_PYTHON_BIN:-python3}}")"
SERVICE_VENV_DIR="$(resolve_service_path "${WAN_SERVICE_VENV_DIR:-.venv}")"

command -v "${PYTHON_BOOTSTRAP_BIN}" >/dev/null 2>&1 || {
  echo "[error] Python executable not found: ${PYTHON_BOOTSTRAP_BIN}" >&2
  exit 1
}

if [[ ! -d "${SERVICE_VENV_DIR}" ]]; then
  echo "[setup] Creating service virtual environment"
  "${PYTHON_BOOTSTRAP_BIN}" -m venv "${SERVICE_VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${SERVICE_VENV_DIR}/bin/activate"

echo "[setup] Upgrading service pip tooling"
python -m pip install --upgrade pip wheel setuptools

echo "[setup] Installing FastAPI service dependencies"
python -m pip install -r "${SERVICE_ROOT}/requirements-service.txt"

echo "[setup] Preparing ComfyUI runtime and models"
bash "${SERVICE_ROOT}/scripts/setup_comfyui.sh"

echo "[done] setup_wan22.sh completed."
