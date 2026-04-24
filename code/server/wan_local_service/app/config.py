from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_NAME = "wan-local-service"
API_MODE_T2V = "t2v"
API_MODE_I2V = "i2v"
API_MODES = (API_MODE_T2V, API_MODE_I2V)
INTERNAL_WAN_TASK = "ti2v-5B"
TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_SUCCEEDED = "succeeded"
TASK_STATUS_FAILED = "failed"
TASK_STATUSES = (
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
    TASK_STATUS_FAILED,
)
RESTARTED_PENDING_MESSAGE = "service restarted before task execution"
RESTARTED_RUNNING_MESSAGE = "service restarted while task was running"
DEFAULT_ALLOWED_SIZES = ("1280*704", "704*1280")
DEFAULT_SIZE = "1280*704"
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 100
TASK_OUTPUT_FILENAME = "result.mp4"
DEFAULT_MAX_INPUT_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_INPUT_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
SUPPORTED_INPUT_IMAGE_CONTENT_TYPES = {
    ".png": ("image/png",),
    ".jpg": ("image/jpeg", "image/jpg"),
    ".jpeg": ("image/jpeg", "image/jpg"),
    ".webp": ("image/webp",),
}


def _parse_env_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_optional_int(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return int(normalized)


def _parse_optional_float(raw_value: str | None) -> float | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    return float(normalized)


def _parse_allowed_sizes(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return DEFAULT_ALLOWED_SIZES
    sizes = tuple(part.strip() for part in raw_value.split(",") if part.strip())
    return sizes or DEFAULT_ALLOWED_SIZES


def _resolve_path(base_dir: Path, raw_value: str | None, default_value: Path) -> Path:
    candidate = Path(raw_value) if raw_value else default_value
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve()


@dataclass(slots=True)
class Settings:
    service_root: Path
    service_host: str
    service_port: int
    db_path: Path
    logs_dir: Path
    outputs_dir: Path
    storage_dir: Path
    third_party_dir: Path
    wan_repo_dir: Path
    wan_model_dir: Path
    wan_generate_py: Path
    python_bin: str
    allowed_sizes: tuple[str, ...]
    default_size: str
    max_input_image_bytes: int
    low_memory_profile: bool
    offload_model: bool
    t5_cpu: bool
    convert_model_dtype: bool
    sample_solver: str
    sample_steps: int | None
    sample_shift: float | None
    sample_guide_scale: float | None
    frame_num: int | None
    runtime_memory_guard_enabled: bool
    min_mem_available_gb: float
    min_swap_available_gb: float

    def ensure_directories(self) -> None:
        for path in (
            self.storage_dir,
            self.logs_dir,
            self.outputs_dir,
            self.third_party_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    service_root = Path(__file__).resolve().parents[1]
    load_dotenv(service_root / ".env", override=False)

    storage_dir = _resolve_path(service_root, os.getenv("WAN_STORAGE_DIR"), Path("storage"))
    logs_dir = _resolve_path(service_root, os.getenv("WAN_LOG_DIR"), Path("logs"))
    outputs_dir = _resolve_path(service_root, os.getenv("WAN_OUTPUT_DIR"), Path("outputs"))
    third_party_dir = _resolve_path(
        service_root,
        os.getenv("WAN_THIRD_PARTY_DIR"),
        Path("third_party"),
    )
    wan_repo_dir = _resolve_path(
        service_root,
        os.getenv("WAN_REPO_DIR"),
        Path("third_party/Wan2.2"),
    )
    wan_model_dir = _resolve_path(
        service_root,
        os.getenv("WAN_MODEL_DIR"),
        Path("third_party/Wan2.2-TI2V-5B"),
    )
    wan_generate_py = _resolve_path(
        service_root,
        os.getenv("WAN_GENERATE_PY"),
        Path("third_party/Wan2.2/generate.py"),
    )
    db_path = _resolve_path(service_root, os.getenv("WAN_DB_PATH"), Path("storage/tasks.db"))
    default_size = (os.getenv("WAN_DEFAULT_SIZE") or DEFAULT_SIZE).strip() or DEFAULT_SIZE
    allowed_sizes = _parse_allowed_sizes(os.getenv("WAN_ALLOWED_SIZES"))
    if default_size not in allowed_sizes:
        default_size = allowed_sizes[0]

    low_memory_profile = _parse_env_bool(os.getenv("WAN_LOW_MEMORY_PROFILE"), False)
    frame_num = _parse_optional_int(os.getenv("WAN_FRAME_NUM"))
    if frame_num is None and low_memory_profile:
        frame_num = 17

    sample_steps = _parse_optional_int(os.getenv("WAN_SAMPLE_STEPS"))
    if sample_steps is None and low_memory_profile:
        sample_steps = 20

    sample_shift = _parse_optional_float(os.getenv("WAN_SAMPLE_SHIFT"))
    sample_guide_scale = _parse_optional_float(os.getenv("WAN_SAMPLE_GUIDE_SCALE"))
    min_mem_available_gb = _parse_optional_float(os.getenv("WAN_MIN_MEM_AVAILABLE_GB"))
    if min_mem_available_gb is None:
        min_mem_available_gb = 4.0 if low_memory_profile else 2.0

    min_swap_available_gb = _parse_optional_float(os.getenv("WAN_MIN_SWAP_AVAILABLE_GB"))
    if min_swap_available_gb is None:
        min_swap_available_gb = 2.0 if low_memory_profile else 1.0

    return Settings(
        service_root=service_root,
        service_host=(os.getenv("WAN_SERVICE_HOST") or "0.0.0.0"),
        service_port=int(os.getenv("WAN_SERVICE_PORT") or "8000"),
        db_path=db_path,
        logs_dir=logs_dir,
        outputs_dir=outputs_dir,
        storage_dir=storage_dir,
        third_party_dir=third_party_dir,
        wan_repo_dir=wan_repo_dir,
        wan_model_dir=wan_model_dir,
        wan_generate_py=wan_generate_py,
        python_bin=os.getenv("WAN_INFERENCE_PYTHON_BIN") or sys.executable,
        allowed_sizes=allowed_sizes,
        default_size=default_size,
        max_input_image_bytes=int(
            os.getenv("WAN_MAX_INPUT_IMAGE_BYTES") or DEFAULT_MAX_INPUT_IMAGE_BYTES
        ),
        low_memory_profile=low_memory_profile,
        offload_model=_parse_env_bool(os.getenv("WAN_OFFLOAD_MODEL"), True),
        t5_cpu=_parse_env_bool(os.getenv("WAN_T5_CPU"), True),
        convert_model_dtype=_parse_env_bool(
            os.getenv("WAN_CONVERT_MODEL_DTYPE"),
            True,
        ),
        sample_solver=(os.getenv("WAN_SAMPLE_SOLVER") or "unipc").strip() or "unipc",
        sample_steps=sample_steps,
        sample_shift=sample_shift,
        sample_guide_scale=sample_guide_scale,
        frame_num=frame_num,
        runtime_memory_guard_enabled=_parse_env_bool(
            os.getenv("WAN_ENFORCE_RUNTIME_MEMORY_GUARD"),
            False,
        ),
        min_mem_available_gb=min_mem_available_gb,
        min_swap_available_gb=min_swap_available_gb,
    )
