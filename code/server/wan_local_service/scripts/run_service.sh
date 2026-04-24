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

resolve_service_python() {
  if [[ -n "${WAN_SERVICE_PYTHON_BIN:-}" ]]; then
    resolve_exec_or_path "${WAN_SERVICE_PYTHON_BIN}"
    return
  fi

  local default_venv_python="${SERVICE_ROOT}/.venv/bin/python"
  if [[ -x "${default_venv_python}" ]]; then
    printf '%s\n' "${default_venv_python}"
    return
  fi

  resolve_exec_or_path "${WAN_PYTHON_BIN:-.venv/bin/python}"
}

if [[ -f "${SERVICE_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SERVICE_ROOT}/.env"
  set +a
fi

COMMAND="${1:-foreground}"
HOST="${WAN_SERVICE_HOST:-0.0.0.0}"
PORT="${WAN_SERVICE_PORT:-8000}"
PYTHON_BIN="$(resolve_service_python)"
WAN_STORAGE_DIR="$(resolve_service_path "${WAN_STORAGE_DIR:-storage}")"
WAN_LOG_DIR="$(resolve_service_path "${WAN_LOG_DIR:-logs}")"
WAN_OUTPUT_DIR="$(resolve_service_path "${WAN_OUTPUT_DIR:-outputs}")"
WAN_THIRD_PARTY_DIR="$(resolve_service_path "${WAN_THIRD_PARTY_DIR:-third_party}")"
SERVICE_PID_FILE="$(resolve_service_path "${WAN_SERVICE_PID_FILE:-storage/service.pid}")"
SERVICE_LOG_FILE="$(resolve_service_path "${WAN_SERVICE_STDOUT_LOG:-logs/service.log}")"
HEALTHCHECK_URL="http://127.0.0.1:${PORT}/healthz"
SKIP_HEALTHCHECK="${WAN_SERVICE_SKIP_HEALTHCHECK:-0}"

mkdir -p \
  "${WAN_STORAGE_DIR}" \
  "${WAN_LOG_DIR}" \
  "${WAN_OUTPUT_DIR}" \
  "${WAN_THIRD_PARTY_DIR}"

python_command_exists() {
  local raw_value="$1"
  if [[ "${raw_value}" == */* ]]; then
    [[ -x "${raw_value}" ]]
  else
    command -v "${raw_value}" >/dev/null 2>&1
  fi
}

validate_service_runtime() {
  if ! python_command_exists "${PYTHON_BIN}"; then
    echo "[error] Service Python not found: ${PYTHON_BIN}" >&2
    echo "[hint] Run: cd ${SERVICE_ROOT} && bash scripts/setup_wan22.sh" >&2
    echo "[hint] Check details with: cd ${SERVICE_ROOT} && bash scripts/check_env.sh" >&2
    return 1
  fi

  if ! PYTHONPATH="${SERVICE_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
    "${PYTHON_BIN}" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    echo "[error] Service runtime dependencies are missing in ${PYTHON_BIN}" >&2
    echo "[hint] Run: cd ${SERVICE_ROOT} && bash scripts/setup_wan22.sh" >&2
    echo "[hint] Check details with: cd ${SERVICE_ROOT} && bash scripts/check_env.sh --require service" >&2
    return 1
  fi
}

read_pid() {
  if [[ ! -f "${SERVICE_PID_FILE}" ]]; then
    return 1
  fi

  local pid
  pid="$(<"${SERVICE_PID_FILE}")"
  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    return 1
  fi

  printf '%s\n' "${pid}"
}

service_is_running() {
  local pid
  if ! pid="$(read_pid)"; then
    return 1
  fi

  if kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi

  rm -f "${SERVICE_PID_FILE}"
  return 1
}

wait_for_healthcheck() {
  if [[ "${SKIP_HEALTHCHECK}" == "1" ]]; then
    return 0
  fi

  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi

  local attempt
  for attempt in {1..20}; do
    if curl --noproxy '*' --fail --silent --show-error "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

start_background_service() {
  validate_service_runtime || return 1

  if service_is_running; then
    local running_pid
    running_pid="$(read_pid)"
    echo "[run] Service already running pid=${running_pid}"
    echo "[run] Health check: ${HEALTHCHECK_URL}"
    return 0
  fi

  cd "${SERVICE_ROOT}"
  if command -v setsid >/dev/null 2>&1; then
    setsid "${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" \
      >"${SERVICE_LOG_FILE}" 2>&1 < /dev/null &
  else
    nohup "${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" \
      >"${SERVICE_LOG_FILE}" 2>&1 < /dev/null &
  fi
  local pid=$!
  printf '%s\n' "${pid}" > "${SERVICE_PID_FILE}"

  sleep 1
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[run] Failed to start service. Check ${SERVICE_LOG_FILE}" >&2
    rm -f "${SERVICE_PID_FILE}"
    tail -n 20 "${SERVICE_LOG_FILE}" >&2 || true
    return 1
  fi

  if ! wait_for_healthcheck; then
    echo "[run] Service process is alive but /healthz is not ready. Check ${SERVICE_LOG_FILE}" >&2
    kill "${pid}" 2>/dev/null || true
    rm -f "${SERVICE_PID_FILE}"
    tail -n 20 "${SERVICE_LOG_FILE}" >&2 || true
    return 1
  fi

  echo "[run] Service started in background pid=${pid}"
  echo "[run] Health check: ${HEALTHCHECK_URL}"
  echo "[run] Runtime log: ${SERVICE_LOG_FILE}"
}

stop_background_service() {
  local pid
  if ! pid="$(read_pid)"; then
    echo "[run] Service is not running"
    rm -f "${SERVICE_PID_FILE}"
    return 0
  fi

  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[run] Service is not running"
    rm -f "${SERVICE_PID_FILE}"
    return 0
  fi

  kill "${pid}"
  for _ in {1..20}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${SERVICE_PID_FILE}"
      echo "[run] Service stopped"
      return 0
    fi
    sleep 0.25
  done

  echo "[run] Service did not stop within timeout. pid=${pid}" >&2
  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${SERVICE_PID_FILE}"
  echo "[run] Service was force-stopped"
  return 0
}

show_status() {
  if service_is_running; then
    local pid
    pid="$(read_pid)"
    echo "[run] Service is running pid=${pid}"
    echo "[run] Health check: ${HEALTHCHECK_URL}"
    echo "[run] Runtime log: ${SERVICE_LOG_FILE}"
    return 0
  fi

  echo "[run] Service is not running"
  return 1
}

case "${COMMAND}" in
  foreground)
    validate_service_runtime
    cd "${SERVICE_ROOT}"
    echo "[run] Starting ${HOST}:${PORT}"
    echo "[run] OpenAPI docs: http://127.0.0.1:${PORT}/docs"
    exec "${PYTHON_BIN}" -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
    ;;
  start)
    start_background_service
    ;;
  stop)
    stop_background_service
    ;;
  status)
    show_status
    ;;
  *)
    echo "Usage: bash scripts/run_service.sh [foreground|start|stop|status]" >&2
    exit 1
    ;;
esac
