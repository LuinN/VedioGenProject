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
COMFYUI_DIR="$(resolve_service_path "${WAN_COMFYUI_DIR:-third_party/ComfyUI}")"
COMFYUI_VENV_DIR="$(resolve_service_path "${WAN_COMFYUI_VENV_DIR:-.comfyui-venv}")"
COMFYUI_PYTHON_BIN="$(resolve_exec_or_path "${WAN_COMFYUI_PYTHON_BIN:-.comfyui-venv/bin/python}")"
COMFYUI_DOWNLOAD_PROVIDER="${WAN_COMFYUI_MODEL_PROVIDER:-${WAN_MODEL_DOWNLOAD_PROVIDER:-huggingface}}"
COMFYUI_AUTO_DOWNLOAD_MODELS="${WAN_COMFYUI_AUTO_DOWNLOAD_MODELS:-${WAN_AUTO_DOWNLOAD_MODEL:-1}}"
COMFYUI_INPUT_DIR="$(resolve_service_path "${WAN_COMFYUI_INPUT_DIR:-storage/comfyui_input}")"
COMFYUI_OUTPUT_DIR="$(resolve_service_path "${WAN_COMFYUI_OUTPUT_DIR:-storage/comfyui_output}")"

mkdir -p "${SERVICE_ROOT}/third_party" "${COMFYUI_INPUT_DIR}" "${COMFYUI_OUTPUT_DIR}"

command -v "${PYTHON_BOOTSTRAP_BIN}" >/dev/null 2>&1 || {
  echo "[error] Python executable not found: ${PYTHON_BOOTSTRAP_BIN}" >&2
  exit 1
}

command -v curl >/dev/null 2>&1 || {
  echo "[error] curl is required but not found." >&2
  exit 1
}

ensure_comfyui_source() {
  if [[ -f "${COMFYUI_DIR}/main.py" ]]; then
    echo "[setup] Reusing existing ComfyUI source: ${COMFYUI_DIR}"
    return
  fi

  rm -rf "${COMFYUI_DIR}"
  if command -v git >/dev/null 2>&1; then
    if git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git "${COMFYUI_DIR}"; then
      echo "[setup] Cloned ComfyUI with git"
      return
    fi
    echo "[warn] git clone failed, falling back to tarball download"
  fi

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' RETURN
  curl -L --fail https://github.com/comfyanonymous/ComfyUI/archive/refs/heads/master.tar.gz -o "${tmp_dir}/comfyui.tar.gz"
  tar -xzf "${tmp_dir}/comfyui.tar.gz" -C "${tmp_dir}"
  mv "${tmp_dir}/ComfyUI-master" "${COMFYUI_DIR}"
  trap - RETURN
  rm -rf "${tmp_dir}"
  echo "[setup] Downloaded ComfyUI tarball"
}

ensure_comfyui_source

if [[ ! -d "${COMFYUI_VENV_DIR}" ]]; then
  echo "[setup] Creating ComfyUI virtual environment"
  "${PYTHON_BOOTSTRAP_BIN}" -m venv "${COMFYUI_VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${COMFYUI_VENV_DIR}/bin/activate"

echo "[setup] Upgrading pip tooling in ${COMFYUI_VENV_DIR}"
python -m pip install --upgrade pip wheel setuptools

if [[ -f "${COMFYUI_DIR}/requirements.txt" ]]; then
  echo "[setup] Installing ComfyUI requirements"
  python -m pip install -r "${COMFYUI_DIR}/requirements.txt"
fi

download_hf_file() {
  local repo_id="$1"
  local remote_path="$2"
  local target_path="$3"
  local staging_dir
  local staged_file

  staging_dir="$(mktemp -d)"
  python -m pip install "huggingface_hub[cli]"
  if command -v hf >/dev/null 2>&1; then
    hf download "${repo_id}" "${remote_path}" --local-dir "${staging_dir}"
  else
    huggingface-cli download "${repo_id}" "${remote_path}" --local-dir "${staging_dir}"
  fi
  staged_file="$(find "${staging_dir}" -type f -name "$(basename "${remote_path}")" | head -n 1 || true)"
  if [[ -z "${staged_file}" || ! -f "${staged_file}" ]]; then
    echo "[error] Failed to locate downloaded Hugging Face file: ${remote_path}" >&2
    rm -rf "${staging_dir}"
    exit 1
  fi

  mkdir -p "$(dirname "${target_path}")"
  mv "${staged_file}" "${target_path}"
  rm -rf "${staging_dir}"
}

download_modelscope_file() {
  local repo_id="$1"
  local remote_path="$2"
  local target_path="$3"
  local staging_dir
  local staged_file

  staging_dir="$(mktemp -d)"
  python -m pip install modelscope
  modelscope download "${repo_id}" --include "${remote_path}" --local_dir "${staging_dir}"
  staged_file="$(find "${staging_dir}" -type f -name "$(basename "${remote_path}")" | head -n 1 || true)"
  if [[ -z "${staged_file}" || ! -f "${staged_file}" ]]; then
    echo "[error] Failed to locate downloaded ModelScope file: ${remote_path}" >&2
    rm -rf "${staging_dir}"
    exit 1
  fi

  mkdir -p "$(dirname "${target_path}")"
  mv "${staged_file}" "${target_path}"
  rm -rf "${staging_dir}"
}

download_if_missing() {
  local target_path="$1"
  local repo_id="$2"
  local remote_path="$3"

  if [[ -f "${target_path}" ]]; then
    echo "[setup] Model already exists: ${target_path}"
    return
  fi

  case "${COMFYUI_DOWNLOAD_PROVIDER}" in
    huggingface)
      download_hf_file "${repo_id}" "${remote_path}" "${target_path}"
      ;;
    modelscope)
      download_modelscope_file "${repo_id}" "${remote_path}" "${target_path}"
      ;;
    *)
      echo "[error] Unsupported WAN_COMFYUI_MODEL_PROVIDER: ${COMFYUI_DOWNLOAD_PROVIDER}" >&2
      exit 1
      ;;
  esac
}

if [[ "${COMFYUI_AUTO_DOWNLOAD_MODELS}" == "1" ]]; then
  echo "[setup] Auto-downloading ComfyUI Wan2.2 I2V 14B model files"
  download_if_missing \
    "${COMFYUI_DIR}/models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors" \
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" \
    "split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
  download_if_missing \
    "${COMFYUI_DIR}/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors" \
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" \
    "split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
  download_if_missing \
    "${COMFYUI_DIR}/models/vae/wan_2.1_vae.safetensors" \
    "Comfy-Org/Wan_2.2_ComfyUI_Repackaged" \
    "split_files/vae/wan_2.1_vae.safetensors"
  download_if_missing \
    "${COMFYUI_DIR}/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" \
    "Comfy-Org/Wan_2.1_ComfyUI_repackaged" \
    "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
else
  echo "[info] Auto model download disabled. Expected files:"
  echo "  ${COMFYUI_DIR}/models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"
  echo "  ${COMFYUI_DIR}/models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"
  echo "  ${COMFYUI_DIR}/models/vae/wan_2.1_vae.safetensors"
  echo "  ${COMFYUI_DIR}/models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"
fi

echo "[done] setup_comfyui.sh completed."
