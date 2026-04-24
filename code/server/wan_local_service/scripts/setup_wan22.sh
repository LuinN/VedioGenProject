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
WAN_REPO_DIR="$(resolve_service_path "${WAN_REPO_DIR:-third_party/Wan2.2}")"
WAN_MODEL_DIR="$(resolve_service_path "${WAN_MODEL_DIR:-third_party/Wan2.2-TI2V-5B}")"
WAN_AUTO_DOWNLOAD_MODEL="${WAN_AUTO_DOWNLOAD_MODEL:-0}"
WAN_MODEL_DOWNLOAD_PROVIDER="${WAN_MODEL_DOWNLOAD_PROVIDER:-huggingface}"
WAN_AUTO_INSTALL_CUDA_TOOLKIT="${WAN_AUTO_INSTALL_CUDA_TOOLKIT:-1}"
WAN_CUDA_TOOLKIT_PACKAGE="${WAN_CUDA_TOOLKIT_PACKAGE:-cuda-toolkit-13-0}"
WAN_SETUPTOOLS_SPEC="${WAN_SETUPTOOLS_SPEC:-setuptools<82}"
WAN_FLASH_ATTN_VERSION="${WAN_FLASH_ATTN_VERSION:-2.8.3}"
WAN_FLASH_ATTN_MAX_JOBS="${WAN_FLASH_ATTN_MAX_JOBS:-1}"
WAN_FLASH_ATTN_CUDA_ARCHS="${WAN_FLASH_ATTN_CUDA_ARCHS:-80}"
WAN_FLASH_ATTN_MEMORY_GUARD="${WAN_FLASH_ATTN_MEMORY_GUARD:-1}"
WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB="${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB:-8}"
WAN_FLASH_ATTN_MIN_SWAP_FREE_GB="${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB:-8}"
WAN_FLASH_ATTN_SPEC="flash-attn==${WAN_FLASH_ATTN_VERSION}"
WAN_LOCAL_ATTENTION_PATCH="${SERVICE_ROOT}/patches/wan2.2_attention_sdpa_fallback.patch"

read_meminfo_kib() {
  local field_name="$1"
  awk -v key="${field_name}:" '$1 == key { print $2; exit }' /proc/meminfo 2>/dev/null || true
}

format_gib_from_kib() {
  local value_kib="${1:-}"
  if [[ -z "${value_kib}" ]]; then
    printf 'unknown\n'
    return
  fi
  awk -v kib="${value_kib}" 'BEGIN { printf "%.1f GiB\n", kib / 1024 / 1024 }'
}

show_memory_headroom() {
  local mem_available_kib
  local swap_free_kib
  mem_available_kib="$(read_meminfo_kib MemAvailable)"
  swap_free_kib="$(read_meminfo_kib SwapFree)"
  echo "[env] MemAvailable=$(format_gib_from_kib "${mem_available_kib}")"
  echo "[env] SwapFree=$(format_gib_from_kib "${swap_free_kib}")"
}

warn_on_memory_heavy_processes() {
  local matching_processes=""
  matching_processes="$(ps -eo pid,comm,rss --sort=-rss 2>/dev/null | awk '
    $2 ~ /^(dockerd|containerd|postgres|ollama|python|node)$/ {
      printf "pid=%s comm=%s rss=%.1fMiB\n", $1, $2, $3 / 1024
    }
  ' | head -n 12)"
  if [[ -n "${matching_processes}" ]]; then
    echo "[warn] Active resident processes with notable memory footprint:"
    printf '%s\n' "${matching_processes}"
  fi
}

check_flash_attn_memory_headroom() {
  if [[ "${WAN_FLASH_ATTN_MEMORY_GUARD}" != "1" ]]; then
    return 0
  fi

  local mem_available_kib
  local swap_free_kib
  local min_mem_available_kib
  local min_swap_free_kib
  mem_available_kib="$(read_meminfo_kib MemAvailable)"
  swap_free_kib="$(read_meminfo_kib SwapFree)"
  min_mem_available_kib="$(awk -v gib="${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB}" 'BEGIN { printf "%.0f\n", gib * 1024 * 1024 }')"
  min_swap_free_kib="$(awk -v gib="${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB}" 'BEGIN { printf "%.0f\n", gib * 1024 * 1024 }')"

  show_memory_headroom
  warn_on_memory_heavy_processes

  if [[ -z "${mem_available_kib}" || -z "${swap_free_kib}" ]]; then
    echo "[warn] Could not read /proc/meminfo. Continuing without flash_attn memory guard."
    return 0
  fi

  if (( mem_available_kib >= min_mem_available_kib && swap_free_kib >= min_swap_free_kib )); then
    return 0
  fi

  echo "[error] Refusing to start flash_attn local build with low memory headroom." >&2
  echo "[error] Required at least ${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB} GiB MemAvailable and ${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB} GiB SwapFree." >&2
  echo "[error] Stop Docker / other WSL services, or override the thresholds only if you accept OOM risk." >&2
  return 1
}

ensure_wan_local_patch_applied() {
  local patch_path="$1"
  if [[ ! -f "${patch_path}" ]]; then
    return 0
  fi

  if git -C "${WAN_REPO_DIR}" apply --reverse --check "${patch_path}" >/dev/null 2>&1; then
    echo "[setup] Wan2.2 local patch already applied: $(basename "${patch_path}")"
    return 0
  fi

  if git -C "${WAN_REPO_DIR}" apply --check "${patch_path}" >/dev/null 2>&1; then
    echo "[setup] Applying Wan2.2 local patch: $(basename "${patch_path}")"
    git -C "${WAN_REPO_DIR}" apply "${patch_path}"
    return 0
  fi

  echo "[error] Could not apply Wan2.2 local patch: ${patch_path}" >&2
  return 1
}

bootstrap_cuda_env() {
  local candidate=""
  if [[ -n "${CUDA_HOME:-}" && -x "${CUDA_HOME}/bin/nvcc" ]]; then
    candidate="${CUDA_HOME}"
  else
    for candidate in \
      "/usr/local/cuda" \
      "/usr/local/cuda-13.0" \
      "/usr/local/cuda-13.1" \
      "/usr/local/cuda-13.2"; do
      if [[ -x "${candidate}/bin/nvcc" ]]; then
        export CUDA_HOME="${candidate}"
        break
      fi
    done
  fi

  if [[ -n "${CUDA_HOME:-}" && -x "${CUDA_HOME}/bin/nvcc" ]]; then
    export PATH="${CUDA_HOME}/bin:${PATH}"
    if [[ -d "${CUDA_HOME}/lib64" ]]; then
      export LD_LIBRARY_PATH="${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"
    fi
  fi
}

bootstrap_cuda_env

echo "[env] Service root: ${SERVICE_ROOT}"
echo "[env] Bootstrap Python: ${PYTHON_BOOTSTRAP_BIN}"
echo "[env] Wan repo dir: ${WAN_REPO_DIR}"
echo "[env] Wan model dir: ${WAN_MODEL_DIR}"
echo "[env] Auto-install CUDA toolkit: ${WAN_AUTO_INSTALL_CUDA_TOOLKIT}"
echo "[env] Setuptools constraint: ${WAN_SETUPTOOLS_SPEC}"
echo "[env] FlashAttention package: ${WAN_FLASH_ATTN_SPEC}"
echo "[env] FlashAttention max jobs: ${WAN_FLASH_ATTN_MAX_JOBS}"
echo "[env] FlashAttention CUDA archs: ${WAN_FLASH_ATTN_CUDA_ARCHS}"
echo "[env] FlashAttention memory guard: ${WAN_FLASH_ATTN_MEMORY_GUARD}"
echo "[env] FlashAttention min MemAvailable: ${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB} GiB"
echo "[env] FlashAttention min SwapFree: ${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB} GiB"
echo "[env] Wan local patch: ${WAN_LOCAL_ATTENTION_PATCH}"

command -v "${PYTHON_BOOTSTRAP_BIN}" >/dev/null 2>&1 || {
  echo "[error] Python executable not found: ${PYTHON_BOOTSTRAP_BIN}" >&2
  exit 1
}
command -v git >/dev/null 2>&1 || {
  echo "[error] git is required but not found." >&2
  exit 1
}
command -v ffmpeg >/dev/null 2>&1 || {
  echo "[error] ffmpeg is required but not found." >&2
  exit 1
}

echo "[check] Python version"
"${PYTHON_BOOTSTRAP_BIN}" --version

echo "[check] WSL kernel"
uname -a

echo "[check] NVIDIA driver access"
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi; then
    echo "[warn] nvidia-smi failed. GPU access is not ready for Wan inference."
  fi
else
  echo "[warn] nvidia-smi is not installed or not on PATH."
fi

echo "[check] CUDA toolkit access"
echo "[info] CUDA_HOME=${CUDA_HOME:-}"
if command -v nvcc >/dev/null 2>&1; then
  nvcc -V
else
  echo "[warn] nvcc is not installed or not on PATH."
  if [[ "${WAN_AUTO_INSTALL_CUDA_TOOLKIT}" == "1" ]]; then
    command -v sudo >/dev/null 2>&1 || {
      echo "[error] sudo is required to auto-install ${WAN_CUDA_TOOLKIT_PACKAGE}, but sudo was not found." >&2
      exit 1
    }
    echo "[setup] Installing ${WAN_CUDA_TOOLKIT_PACKAGE} because nvcc is missing"
    sudo apt-get update
    sudo apt-get install -y "${WAN_CUDA_TOOLKIT_PACKAGE}"
    bootstrap_cuda_env
  fi
fi

if command -v nvcc >/dev/null 2>&1; then
  nvcc -V
else
  echo "[hint] Recommended fix path for the current torch cu130 environment:"
  echo "  sudo apt-get update"
  echo "  sudo apt-get install -y ${WAN_CUDA_TOOLKIT_PACKAGE}"
  echo "  export CUDA_HOME=/usr/local/cuda-13.0"
  echo "  export PATH=\"\${CUDA_HOME}/bin:\${PATH}\""
  exit 1
fi

if [[ ! -d "${SERVICE_ROOT}/.venv" ]]; then
  echo "[setup] Creating virtual environment"
  "${PYTHON_BOOTSTRAP_BIN}" -m venv "${SERVICE_ROOT}/.venv"
fi

# shellcheck disable=SC1091
source "${SERVICE_ROOT}/.venv/bin/activate"

echo "[setup] Upgrading pip tooling"
python -m pip install --upgrade pip wheel

echo "[setup] Pinning setuptools for torch 2.11 compatibility"
python -m pip install --force-reinstall "${WAN_SETUPTOOLS_SPEC}"

echo "[setup] Installing Python build dependencies required by flash-attn"
python -m pip install packaging psutil ninja

echo "[setup] Installing service dependencies"
python -m pip install -r "${SERVICE_ROOT}/requirements-service.txt"

if [[ -d "${WAN_REPO_DIR}/.git" ]]; then
  echo "[setup] Updating Wan2.2 repository"
  git -C "${WAN_REPO_DIR}" pull --ff-only
else
  echo "[setup] Cloning Wan2.2 repository"
  git clone https://github.com/Wan-Video/Wan2.2.git "${WAN_REPO_DIR}"
fi

ensure_wan_local_patch_applied "${WAN_LOCAL_ATTENTION_PATCH}"

echo "[setup] Installing Wan2.2 requirements"
WAN_REQ_TMP="$(mktemp)"
grep -v '^flash_attn$' "${WAN_REPO_DIR}/requirements.txt" > "${WAN_REQ_TMP}"
python -m pip install -r "${WAN_REQ_TMP}"
rm -f "${WAN_REQ_TMP}"

echo "[setup] Installing runtime dependencies missing from upstream main requirements"
python -m pip install einops decord librosa peft

echo "[setup] Re-applying setuptools constraint after upstream installs"
python -m pip install --force-reinstall "${WAN_SETUPTOOLS_SPEC}"

echo "[setup] Installing ${WAN_FLASH_ATTN_SPEC} without build isolation"
export MAX_JOBS="${MAX_JOBS:-${WAN_FLASH_ATTN_MAX_JOBS}}"
export NINJA_NUM_PROCESSES="${NINJA_NUM_PROCESSES:-${MAX_JOBS}}"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-${MAX_JOBS}}"
echo "[env] MAX_JOBS=${MAX_JOBS}"
echo "[env] NINJA_NUM_PROCESSES=${NINJA_NUM_PROCESSES}"
echo "[env] CMAKE_BUILD_PARALLEL_LEVEL=${CMAKE_BUILD_PARALLEL_LEVEL}"
if grep -qi microsoft /proc/version 2>/dev/null && [[ "${MAX_JOBS}" != "1" ]]; then
  echo "[warn] WSL local flash_attn builds have previously hit global OOM with higher parallelism."
  echo "[warn] Keep MAX_JOBS=1 unless you have verified enough free memory and swap headroom."
fi
check_flash_attn_memory_headroom
if ! \
  WAN_FLASH_ATTN_VERSION="${WAN_FLASH_ATTN_VERSION}" \
  WAN_FLASH_ATTN_MAX_JOBS="${WAN_FLASH_ATTN_MAX_JOBS}" \
  WAN_FLASH_ATTN_CUDA_ARCHS="${WAN_FLASH_ATTN_CUDA_ARCHS}" \
  WAN_FLASH_ATTN_MEMORY_GUARD="${WAN_FLASH_ATTN_MEMORY_GUARD}" \
  WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB="${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB}" \
  WAN_FLASH_ATTN_MIN_SWAP_FREE_GB="${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB}" \
  WAN_PYTHON_SETUP_BIN="${PYTHON_BOOTSTRAP_BIN}" \
  bash "${SERVICE_ROOT}/scripts/build_flash_attn_resumable.sh" resume; then
  echo "[error] flash_attn installation failed after installing the other Wan2.2 requirements." >&2
  echo "[error] This is a real blocker. Check the pip output above for the exact failure." >&2
  exit 1
fi

if [[ "${WAN_AUTO_DOWNLOAD_MODEL}" == "1" ]]; then
  echo "[setup] WAN_AUTO_DOWNLOAD_MODEL=1, downloading model weights"
  mkdir -p "${WAN_MODEL_DIR}"
  if [[ "${WAN_MODEL_DOWNLOAD_PROVIDER}" == "huggingface" ]]; then
    python -m pip install "huggingface_hub[cli]"
    huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir "${WAN_MODEL_DIR}"
  elif [[ "${WAN_MODEL_DOWNLOAD_PROVIDER}" == "modelscope" ]]; then
    python -m pip install modelscope
    modelscope download Wan-AI/Wan2.2-TI2V-5B --local_dir "${WAN_MODEL_DIR}"
  else
    echo "[error] Unsupported WAN_MODEL_DOWNLOAD_PROVIDER: ${WAN_MODEL_DOWNLOAD_PROVIDER}" >&2
    exit 1
  fi
else
  echo "[info] Model auto-download is disabled."
  echo "[info] Download manually with one of the official commands:"
  echo "  huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir \"${WAN_MODEL_DIR}\""
  echo "  modelscope download Wan-AI/Wan2.2-TI2V-5B --local_dir \"${WAN_MODEL_DIR}\""
fi

echo "[done] setup_wan22.sh completed."
