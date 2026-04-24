#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ACTION="${1:-resume}"

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

WAN_FLASH_ATTN_VERSION="${WAN_FLASH_ATTN_VERSION:-2.8.3}"
WAN_FLASH_ATTN_SPEC="flash-attn==${WAN_FLASH_ATTN_VERSION}"
WAN_FLASH_ATTN_SRC_DIR="$(resolve_service_path "${WAN_FLASH_ATTN_SRC_DIR:-third_party/flash-attn-${WAN_FLASH_ATTN_VERSION}-src}")"
WAN_FLASH_ATTN_WHEEL_DIR="$(resolve_service_path "${WAN_FLASH_ATTN_WHEEL_DIR:-storage/flash_attn_wheels}")"
WAN_FLASH_ATTN_DOWNLOAD_DIR="$(resolve_service_path "${WAN_FLASH_ATTN_DOWNLOAD_DIR:-storage/flash_attn_sdists}")"
WAN_FLASH_ATTN_MAX_JOBS="${WAN_FLASH_ATTN_MAX_JOBS:-1}"
WAN_FLASH_ATTN_CUDA_ARCHS="${WAN_FLASH_ATTN_CUDA_ARCHS:-80}"
WAN_FLASH_ATTN_MEMORY_GUARD="${WAN_FLASH_ATTN_MEMORY_GUARD:-1}"
WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB="${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB:-8}"
WAN_FLASH_ATTN_MIN_SWAP_FREE_GB="${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB:-8}"
PYTHON_BIN="$(resolve_exec_or_path "${WAN_PYTHON_SETUP_BIN:-${WAN_PYTHON_BIN:-python3}}")"

if [[ -x "${SERVICE_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${SERVICE_ROOT}/.venv/bin/python"
fi

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

  echo "[error] Refusing to resume flash_attn local build with low memory headroom." >&2
  echo "[error] Required at least ${WAN_FLASH_ATTN_MIN_MEM_AVAILABLE_GB} GiB MemAvailable and ${WAN_FLASH_ATTN_MIN_SWAP_FREE_GB} GiB SwapFree." >&2
  echo "[error] Stop Docker / other WSL services, or override the thresholds only if you accept OOM risk." >&2
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

ensure_build_prereqs() {
  command -v "${PYTHON_BIN}" >/dev/null 2>&1 || {
    echo "[error] Python executable not found: ${PYTHON_BIN}" >&2
    exit 1
  }
  bootstrap_cuda_env
  command -v nvcc >/dev/null 2>&1 || {
    echo "[error] nvcc is not available on PATH. Set CUDA_HOME first or run scripts/setup_wan22.sh." >&2
    exit 1
  }
  "${PYTHON_BIN}" -c 'import packaging, psutil, ninja, torch, wheel, setuptools' >/dev/null 2>&1 || {
    echo "[error] Missing Python build/runtime dependencies in the service environment." >&2
    echo "[error] Run bash scripts/setup_wan22.sh once to restore the expected .venv contents." >&2
    exit 1
  }
}

ensure_source_tree() {
  if [[ -f "${WAN_FLASH_ATTN_SRC_DIR}/setup.py" ]]; then
    return 0
  fi

  echo "[setup] Persistent flash_attn source tree is missing. Downloading sdist for ${WAN_FLASH_ATTN_SPEC}."
  mkdir -p "$(dirname "${WAN_FLASH_ATTN_SRC_DIR}")" "${WAN_FLASH_ATTN_DOWNLOAD_DIR}"
  "${PYTHON_BIN}" -m pip download --no-binary :all: --no-deps -d "${WAN_FLASH_ATTN_DOWNLOAD_DIR}" "${WAN_FLASH_ATTN_SPEC}"

  local sdist_path=""
  local extract_dir=""
  local extracted_root=""
  sdist_path="$(find "${WAN_FLASH_ATTN_DOWNLOAD_DIR}" -maxdepth 1 -type f \( -name "flash_attn-${WAN_FLASH_ATTN_VERSION}*.tar.gz" -o -name "flash_attn-${WAN_FLASH_ATTN_VERSION}*.zip" \) | sort | tail -n 1)"
  if [[ -z "${sdist_path}" ]]; then
    echo "[error] Could not locate a downloaded source archive for ${WAN_FLASH_ATTN_SPEC}." >&2
    exit 1
  fi

  extract_dir="$(mktemp -d "${TMPDIR:-/tmp}/flash-attn-extract.XXXXXX")"
  case "${sdist_path}" in
    *.tar.gz)
      tar -xzf "${sdist_path}" -C "${extract_dir}"
      ;;
    *.zip)
      unzip -q "${sdist_path}" -d "${extract_dir}"
      ;;
    *)
      echo "[error] Unsupported source archive format: ${sdist_path}" >&2
      rm -rf "${extract_dir}"
      exit 1
      ;;
  esac

  extracted_root="$(find "${extract_dir}" -mindepth 1 -maxdepth 1 -type d | sort | head -n 1)"
  if [[ -z "${extracted_root}" ]]; then
    echo "[error] Source archive did not contain an extractable root directory." >&2
    rm -rf "${extract_dir}"
    exit 1
  fi

  rm -rf "${WAN_FLASH_ATTN_SRC_DIR}"
  mv "${extracted_root}" "${WAN_FLASH_ATTN_SRC_DIR}"
  rm -rf "${extract_dir}"
}

current_build_dir() {
  if [[ ! -d "${WAN_FLASH_ATTN_SRC_DIR}/build" ]]; then
    return 0
  fi
  find "${WAN_FLASH_ATTN_SRC_DIR}/build" -maxdepth 1 -type d -name 'temp.linux-*' | sort | tail -n 1
}

current_build_ninja() {
  local build_dir=""
  build_dir="$(current_build_dir)"
  if [[ -n "${build_dir}" && -f "${build_dir}/build.ninja" ]]; then
    printf '%s\n' "${build_dir}/build.ninja"
  fi
}

mapped_root_from_log() {
  local log_path="$1"
  local recorded_output=""
  recorded_output="$(awk -F '\t' 'NR > 1 && $4 != "" { print $4; exit }' "${log_path}")"
  if [[ -z "${recorded_output}" ]]; then
    return 0
  fi
  if [[ "${recorded_output}" != *"/build/temp.linux-"* ]]; then
    return 0
  fi
  printf '%s\n' "${recorded_output%%/build/temp.linux-*}"
}

prepare_legacy_build_root() {
  local build_dir=""
  local recorded_log=""
  local recorded_root=""

  FLASH_ATTN_BUILD_ROOT="${WAN_FLASH_ATTN_SRC_DIR}"
  build_dir="$(current_build_dir)"
  if [[ -z "${build_dir}" ]]; then
    return 0
  fi

  if [[ -f "${build_dir}/.ninja_log.pre_migrate" ]]; then
    recorded_log="${build_dir}/.ninja_log.pre_migrate"
  elif [[ -f "${build_dir}/.ninja_log" ]]; then
    recorded_log="${build_dir}/.ninja_log"
  else
    return 0
  fi

  recorded_root="$(mapped_root_from_log "${recorded_log}")"
  if [[ -z "${recorded_root}" || "${recorded_root}" == "${WAN_FLASH_ATTN_SRC_DIR}" ]]; then
    return 0
  fi

  if [[ -e "${recorded_root}" && ! -L "${recorded_root}" && "${recorded_root}" != "${WAN_FLASH_ATTN_SRC_DIR}" ]]; then
    echo "[warn] Legacy build root already exists and is not a symlink: ${recorded_root}"
    echo "[warn] Falling back to the persistent source root; ninja may rebuild completed objects."
    return 0
  fi

  mkdir -p "$(dirname "${recorded_root}")"
  ln -sfn "${WAN_FLASH_ATTN_SRC_DIR}" "${recorded_root}"
  if [[ -f "${build_dir}/.ninja_log.pre_migrate" ]]; then
    cp -f "${build_dir}/.ninja_log.pre_migrate" "${build_dir}/.ninja_log"
  fi
  FLASH_ATTN_BUILD_ROOT="${recorded_root}"
  echo "[fix] Using legacy build alias root: ${FLASH_ATTN_BUILD_ROOT}"
}

print_status() {
  local build_dir=""
  local build_ninja=""
  local built_objects="0"
  local total_targets="0"
  local latest_object=""
  local wheel_listing=""

  build_dir="$(current_build_dir)"
  build_ninja="$(current_build_ninja)"

  echo "[status] flash_attn source dir: ${WAN_FLASH_ATTN_SRC_DIR}"
  echo "[status] flash_attn wheel dir: ${WAN_FLASH_ATTN_WHEEL_DIR}"
  if [[ -n "${build_dir}" ]]; then
    built_objects="$(find "${build_dir}" -name '*.o' | wc -l | tr -d ' ')"
    echo "[status] build dir: ${build_dir}"
  else
    echo "[status] build dir: not created yet"
  fi

  if [[ -n "${build_ninja}" ]]; then
    total_targets="$(awk '/^build .*\.o:/{count++} END{print count+0}' "${build_ninja}")"
  fi
  echo "[status] compiled objects: ${built_objects}/${total_targets}"

  if [[ -n "${build_dir}" ]]; then
    latest_object="$(find "${build_dir}" -name '*.o' -printf '%TY-%Tm-%Td %TT %p\n' | sort | tail -n 1)"
  fi
  if [[ -n "${latest_object}" ]]; then
    echo "[status] latest object: ${latest_object}"
  fi

  wheel_listing="$(find "${WAN_FLASH_ATTN_WHEEL_DIR}" -maxdepth 1 -type f -name 'flash_attn-*.whl' -printf '%TY-%Tm-%Td %TT %p\n' | sort | tail -n 3)"
  if [[ -n "${wheel_listing}" ]]; then
    echo "[status] existing wheels:"
    printf '%s\n' "${wheel_listing}"
  fi
}

resume_build() {
  ensure_build_prereqs
  ensure_source_tree
  prepare_legacy_build_root
  check_flash_attn_memory_headroom
  mkdir -p "${WAN_FLASH_ATTN_WHEEL_DIR}"

  export MAX_JOBS="${MAX_JOBS:-${WAN_FLASH_ATTN_MAX_JOBS}}"
  export NINJA_NUM_PROCESSES="${NINJA_NUM_PROCESSES:-${MAX_JOBS}}"
  export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-${MAX_JOBS}}"
  export FLASH_ATTN_CUDA_ARCHS="${FLASH_ATTN_CUDA_ARCHS:-${WAN_FLASH_ATTN_CUDA_ARCHS}}"

  echo "[env] Python: ${PYTHON_BIN}"
  echo "[env] CUDA_HOME=${CUDA_HOME:-}"
  echo "[env] Build root: ${FLASH_ATTN_BUILD_ROOT}"
  echo "[env] MAX_JOBS=${MAX_JOBS}"
  echo "[env] FLASH_ATTN_CUDA_ARCHS=${FLASH_ATTN_CUDA_ARCHS}"
  echo "[env] NINJA_NUM_PROCESSES=${NINJA_NUM_PROCESSES}"
  echo "[env] CMAKE_BUILD_PARALLEL_LEVEL=${CMAKE_BUILD_PARALLEL_LEVEL}"
  print_status

  (
    cd "${FLASH_ATTN_BUILD_ROOT}"
    "${PYTHON_BIN}" setup.py bdist_wheel --dist-dir "${WAN_FLASH_ATTN_WHEEL_DIR}"
  )

  local latest_wheel=""
  latest_wheel="$(find "${WAN_FLASH_ATTN_WHEEL_DIR}" -maxdepth 1 -type f -name 'flash_attn-*.whl' | sort | tail -n 1)"
  if [[ -z "${latest_wheel}" ]]; then
    echo "[error] bdist_wheel finished without producing a wheel." >&2
    exit 1
  fi

  echo "[install] Installing ${latest_wheel}"
  "${PYTHON_BIN}" -m pip install --force-reinstall --no-deps "${latest_wheel}"
  echo "[done] flash_attn resumable build completed and wheel installed."
}

case "${ACTION}" in
  status)
    print_status
    ;;
  resume|build)
    resume_build
    ;;
  *)
    echo "Usage: bash scripts/build_flash_attn_resumable.sh [status|resume]" >&2
    exit 1
    ;;
esac
