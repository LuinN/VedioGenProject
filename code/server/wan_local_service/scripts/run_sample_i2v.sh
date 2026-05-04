#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${SERVICE_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SERVICE_ROOT}/.env"
  set +a
fi

BASE_URL="${WAN_SAMPLE_BASE_URL:-http://127.0.0.1:${WAN_SERVICE_PORT:-8000}}"
PROMPT="${WAN_SAMPLE_PROMPT:-A determined fantasy warrior stands still while the camera slowly moves closer, cinematic lighting, smooth motion}"
SIZE="${WAN_SAMPLE_SIZE:-${WAN_DEFAULT_SIZE:-832*480}}"
IMAGE_PATH="${WAN_SAMPLE_IMAGE:-}"
POLL_INTERVAL="${WAN_SAMPLE_POLL_INTERVAL:-2}"
MAX_POLLS="${WAN_SAMPLE_MAX_POLLS:-1800}"
JSON_PYTHON="${WAN_SAMPLE_JSON_PYTHON:-python3}"
CURL_COMMON=(--noproxy '*' --fail --silent --show-error)

if [[ -z "${IMAGE_PATH}" ]]; then
  echo "[sample] Set WAN_SAMPLE_IMAGE to an input image path before running this script." >&2
  exit 1
fi
if [[ ! -f "${IMAGE_PATH}" ]]; then
  echo "[sample] Input image not found: ${IMAGE_PATH}" >&2
  exit 1
fi

echo "[sample] Checking ${BASE_URL}/healthz"
curl "${CURL_COMMON[@]}" "${BASE_URL}/healthz"
echo

echo "[sample] Creating i2v task"
CREATE_RESPONSE="$(curl --fail --silent --show-error \
  "${CURL_COMMON[@]}" \
  -X POST "${BASE_URL}/api/tasks" \
  -F mode=i2v \
  -F prompt="${PROMPT}" \
  -F size="${SIZE}" \
  -F image=@"${IMAGE_PATH}")"
echo "${CREATE_RESPONSE}"

TASK_ID="$(
  printf '%s' "${CREATE_RESPONSE}" | "${JSON_PYTHON}" -c 'import json,sys; print(json.load(sys.stdin)["task_id"])'
)"
echo "[sample] task_id=${TASK_ID}"

for (( attempt=1; attempt<=MAX_POLLS; attempt++ )); do
  TASK_RESPONSE="$(curl "${CURL_COMMON[@]}" "${BASE_URL}/api/tasks/${TASK_ID}")"
  mapfile -t TASK_FIELDS < <(
    printf '%s' "${TASK_RESPONSE}" | "${JSON_PYTHON}" -c '
import json
import sys

payload = json.load(sys.stdin)
fields = [
    payload.get("status") or "",
    payload.get("output_path") or "",
    payload.get("error_message") or "",
    payload.get("status_message") or "",
    payload.get("backend_prompt_id") or "",
    "" if payload.get("progress_current") is None else str(payload["progress_current"]),
    "" if payload.get("progress_total") is None else str(payload["progress_total"]),
    "" if payload.get("progress_percent") is None else str(payload["progress_percent"]),
]
for field in fields:
    print(field)
'
  )
  STATUS="${TASK_FIELDS[0]:-}"
  OUTPUT_PATH="${TASK_FIELDS[1]:-}"
  ERROR_MESSAGE="${TASK_FIELDS[2]:-}"
  STATUS_MESSAGE="${TASK_FIELDS[3]:-}"
  BACKEND_PROMPT_ID="${TASK_FIELDS[4]:-}"
  PROGRESS_CURRENT="${TASK_FIELDS[5]:-}"
  PROGRESS_TOTAL="${TASK_FIELDS[6]:-}"
  PROGRESS_PERCENT="${TASK_FIELDS[7]:-}"
  PROGRESS_TEXT=""
  if [[ -n "${PROGRESS_CURRENT}" && -n "${PROGRESS_TOTAL}" ]]; then
    PROGRESS_TEXT=" progress=${PROGRESS_CURRENT}/${PROGRESS_TOTAL}"
  fi
  if [[ -n "${PROGRESS_PERCENT}" ]]; then
    PROGRESS_TEXT="${PROGRESS_TEXT} (${PROGRESS_PERCENT}%)"
  fi
  echo "[sample] poll=${attempt} status=${STATUS} stage=${STATUS_MESSAGE:-unknown}${PROGRESS_TEXT} backend_prompt_id=${BACKEND_PROMPT_ID:-unknown}"
  if [[ "${STATUS}" == "succeeded" ]]; then
    echo "[sample] output_path=${OUTPUT_PATH}"
    exit 0
  fi
  if [[ "${STATUS}" == "failed" ]]; then
    echo "[sample] error_message=${ERROR_MESSAGE}"
    exit 1
  fi
  sleep "${POLL_INTERVAL}"
done

echo "[sample] Timed out waiting for task ${TASK_ID}" >&2
exit 1
