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
PROMPT="${WAN_SAMPLE_PROMPT:-A cinematic cyberpunk street at night, slow camera push-in, rain reflections on the ground}"
SIZE="${WAN_SAMPLE_SIZE:-${WAN_DEFAULT_SIZE:-1280*704}}"
POLL_INTERVAL="${WAN_SAMPLE_POLL_INTERVAL:-2}"
MAX_POLLS="${WAN_SAMPLE_MAX_POLLS:-180}"
JSON_PYTHON="${WAN_SAMPLE_JSON_PYTHON:-python3}"
CURL_COMMON=(--noproxy '*' --fail --silent --show-error)

echo "[sample] Checking ${BASE_URL}/healthz"
curl "${CURL_COMMON[@]}" "${BASE_URL}/healthz"
echo

PAYLOAD="$(
  WAN_SAMPLE_PROMPT_VALUE="${PROMPT}" \
  WAN_SAMPLE_SIZE_VALUE="${SIZE}" \
  "${JSON_PYTHON}" -c 'import json, os; print(json.dumps({"mode": "t2v", "prompt": os.environ["WAN_SAMPLE_PROMPT_VALUE"], "size": os.environ["WAN_SAMPLE_SIZE_VALUE"]}))'
)"

echo "[sample] Creating task"
CREATE_RESPONSE="$(curl --fail --silent --show-error \
  "${CURL_COMMON[@]}" \
  -H "Content-Type: application/json" \
  -X POST "${BASE_URL}/api/tasks" \
  -d "${PAYLOAD}")"
echo "${CREATE_RESPONSE}"

TASK_ID="$(
  printf '%s' "${CREATE_RESPONSE}" | "${JSON_PYTHON}" -c 'import json,sys; print(json.load(sys.stdin)["task_id"])'
)"
echo "[sample] task_id=${TASK_ID}"

for (( attempt=1; attempt<=MAX_POLLS; attempt++ )); do
  TASK_RESPONSE="$(curl "${CURL_COMMON[@]}" "${BASE_URL}/api/tasks/${TASK_ID}")"
  STATUS="$(
    printf '%s' "${TASK_RESPONSE}" | "${JSON_PYTHON}" -c 'import json,sys; print(json.load(sys.stdin)["status"])'
  )"
  echo "[sample] poll=${attempt} status=${STATUS}"
  if [[ "${STATUS}" == "succeeded" ]]; then
    OUTPUT_PATH="$(
      printf '%s' "${TASK_RESPONSE}" | "${JSON_PYTHON}" -c 'import json,sys; print(json.load(sys.stdin)["output_path"])'
    )"
    echo "[sample] output_path=${OUTPUT_PATH}"
    exit 0
  fi
  if [[ "${STATUS}" == "failed" ]]; then
    ERROR_MESSAGE="$(
      printf '%s' "${TASK_RESPONSE}" | "${JSON_PYTHON}" -c 'import json,sys; print(json.load(sys.stdin)["error_message"])'
    )"
    echo "[sample] error_message=${ERROR_MESSAGE}"
    exit 1
  fi
  sleep "${POLL_INTERVAL}"
done

echo "[sample] Timed out waiting for task ${TASK_ID}" >&2
exit 1
