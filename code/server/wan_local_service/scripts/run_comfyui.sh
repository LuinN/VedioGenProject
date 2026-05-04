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

COMMAND="${1:-foreground}"
COMFYUI_DIR="$(resolve_service_path "${WAN_COMFYUI_DIR:-third_party/ComfyUI}")"
COMFYUI_PYTHON_BIN="$(resolve_exec_or_path "${WAN_COMFYUI_PYTHON_BIN:-.comfyui-venv/bin/python}")"
COMFYUI_HOST="${WAN_COMFYUI_HOST:-127.0.0.1}"
COMFYUI_PORT="${WAN_COMFYUI_PORT:-8188}"
COMFYUI_INPUT_DIR="$(resolve_service_path "${WAN_COMFYUI_INPUT_DIR:-storage/comfyui_input}")"
COMFYUI_OUTPUT_DIR="$(resolve_service_path "${WAN_COMFYUI_OUTPUT_DIR:-storage/comfyui_output}")"
COMFYUI_PID_FILE="$(resolve_service_path "${WAN_COMFYUI_PID_FILE:-storage/comfyui.pid}")"
COMFYUI_LOG_FILE="$(resolve_service_path "${WAN_COMFYUI_STDOUT_LOG:-logs/comfyui.log}")"
HEALTHCHECK_URL="http://${COMFYUI_HOST}:${COMFYUI_PORT}/object_info"

mkdir -p "$(dirname "${COMFYUI_PID_FILE}")" "$(dirname "${COMFYUI_LOG_FILE}")" "${COMFYUI_INPUT_DIR}" "${COMFYUI_OUTPUT_DIR}"

python_command_exists() {
  local raw_value="$1"
  if [[ "${raw_value}" == */* ]]; then
    [[ -x "${raw_value}" ]]
  else
    command -v "${raw_value}" >/dev/null 2>&1
  fi
}

validate_comfyui_runtime() {
  if [[ ! -f "${COMFYUI_DIR}/main.py" ]]; then
    echo "[error] ComfyUI source not found: ${COMFYUI_DIR}/main.py" >&2
    echo "[hint] Run: cd ${SERVICE_ROOT} && bash scripts/setup_comfyui.sh" >&2
    return 1
  fi

  if ! python_command_exists "${COMFYUI_PYTHON_BIN}"; then
    echo "[error] ComfyUI Python not found: ${COMFYUI_PYTHON_BIN}" >&2
    echo "[hint] Run: cd ${SERVICE_ROOT} && bash scripts/setup_comfyui.sh" >&2
    return 1
  fi

  if ! "${COMFYUI_PYTHON_BIN}" -c "import aiohttp, PIL, torch" >/dev/null 2>&1; then
    echo "[error] ComfyUI runtime dependencies are missing in ${COMFYUI_PYTHON_BIN}" >&2
    echo "[hint] Run: cd ${SERVICE_ROOT} && bash scripts/setup_comfyui.sh" >&2
    return 1
  fi
}

read_pid() {
  if [[ ! -f "${COMFYUI_PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(<"${COMFYUI_PID_FILE}")"
  if [[ ! "${pid}" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  printf '%s\n' "${pid}"
}

comfyui_is_running() {
  local pid
  if ! pid="$(read_pid)"; then
    return 1
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  rm -f "${COMFYUI_PID_FILE}"
  return 1
}

wait_for_healthcheck() {
  if ! command -v curl >/dev/null 2>&1; then
    return 0
  fi
  local attempt
  for attempt in {1..40}; do
    if curl --noproxy '*' --fail --silent --show-error "${HEALTHCHECK_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

start_background_comfyui() {
  validate_comfyui_runtime || return 1

  if comfyui_is_running; then
    local running_pid
    running_pid="$(read_pid)"
    echo "[run] ComfyUI already running pid=${running_pid}"
    echo "[run] Health check: ${HEALTHCHECK_URL}"
    return 0
  fi

  cd "${COMFYUI_DIR}"
  if command -v setsid >/dev/null 2>&1; then
    setsid "${COMFYUI_PYTHON_BIN}" main.py \
      --listen "${COMFYUI_HOST}" \
      --port "${COMFYUI_PORT}" \
      --input-directory "${COMFYUI_INPUT_DIR}" \
      --output-directory "${COMFYUI_OUTPUT_DIR}" \
      >"${COMFYUI_LOG_FILE}" 2>&1 < /dev/null &
  else
    nohup "${COMFYUI_PYTHON_BIN}" main.py \
      --listen "${COMFYUI_HOST}" \
      --port "${COMFYUI_PORT}" \
      --input-directory "${COMFYUI_INPUT_DIR}" \
      --output-directory "${COMFYUI_OUTPUT_DIR}" \
      >"${COMFYUI_LOG_FILE}" 2>&1 < /dev/null &
  fi
  local pid=$!
  printf '%s\n' "${pid}" > "${COMFYUI_PID_FILE}"

  sleep 1
  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[run] Failed to start ComfyUI. Check ${COMFYUI_LOG_FILE}" >&2
    rm -f "${COMFYUI_PID_FILE}"
    tail -n 20 "${COMFYUI_LOG_FILE}" >&2 || true
    return 1
  fi

  if ! wait_for_healthcheck; then
    echo "[run] ComfyUI process is alive but /object_info is not ready. Check ${COMFYUI_LOG_FILE}" >&2
    kill "${pid}" 2>/dev/null || true
    rm -f "${COMFYUI_PID_FILE}"
    tail -n 40 "${COMFYUI_LOG_FILE}" >&2 || true
    return 1
  fi

  echo "[run] ComfyUI started in background pid=${pid}"
  echo "[run] Health check: ${HEALTHCHECK_URL}"
  echo "[run] Runtime log: ${COMFYUI_LOG_FILE}"
}

stop_background_comfyui() {
  local pid
  if ! pid="$(read_pid)"; then
    echo "[run] ComfyUI is not running"
    rm -f "${COMFYUI_PID_FILE}"
    return 0
  fi

  if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[run] ComfyUI is not running"
    rm -f "${COMFYUI_PID_FILE}"
    return 0
  fi

  kill "${pid}"
  for _ in {1..40}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${COMFYUI_PID_FILE}"
      echo "[run] ComfyUI stopped"
      return 0
    fi
    sleep 0.25
  done

  echo "[run] ComfyUI did not stop within timeout. pid=${pid}" >&2
  kill -9 "${pid}" 2>/dev/null || true
  rm -f "${COMFYUI_PID_FILE}"
  echo "[run] ComfyUI was force-stopped"
}

show_status() {
  if comfyui_is_running; then
    local pid
    pid="$(read_pid)"
    echo "[run] ComfyUI is running pid=${pid}"
    echo "[run] Health check: ${HEALTHCHECK_URL}"
    echo "[run] Runtime log: ${COMFYUI_LOG_FILE}"
    return 0
  fi
  echo "[run] ComfyUI is not running"
  return 1
}

case "${COMMAND}" in
  foreground)
    validate_comfyui_runtime
    cd "${COMFYUI_DIR}"
    exec "${COMFYUI_PYTHON_BIN}" main.py \
      --listen "${COMFYUI_HOST}" \
      --port "${COMFYUI_PORT}" \
      --input-directory "${COMFYUI_INPUT_DIR}" \
      --output-directory "${COMFYUI_OUTPUT_DIR}"
    ;;
  start)
    start_background_comfyui
    ;;
  stop)
    stop_background_comfyui
    ;;
  status)
    show_status
    ;;
  *)
    echo "Usage: bash scripts/run_comfyui.sh [foreground|start|stop|status]" >&2
    exit 1
    ;;
esac
