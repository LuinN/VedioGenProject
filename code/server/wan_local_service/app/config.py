from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

SERVICE_NAME = "wan-local-service"
BACKEND_ID_COMFYUI_NATIVE = "comfyui_native"

API_MODE_T2V = "t2v"
API_MODE_I2V = "i2v"
API_MODES = (API_MODE_T2V, API_MODE_I2V)
SUPPORTED_CREATE_MODES = (API_MODE_I2V,)

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

DEFAULT_ALLOWED_SIZES = ("832*480", "480*832")
DEFAULT_SIZE = "832*480"
DEFAULT_VIDEO_LENGTH = 49
DEFAULT_VIDEO_FPS = 16

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

DEFAULT_NEGATIVE_PROMPT: Final[str] = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，整体发灰，"
    "最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，画得不好的手部，画得不好的脸部，"
    "畸形的，毁容的，形态畸形的肢体，手指融合，静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

COMFYUI_REQUIRED_MODEL_RELATIVE_PATHS: Final[tuple[Path, ...]] = (
    Path("models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors"),
    Path("models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors"),
    Path("models/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors"),
    Path("models/vae/wan_2.1_vae.safetensors"),
)


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


def _resolve_exec_or_path(base_dir: Path, raw_value: str | None, default_value: str) -> str:
    candidate = raw_value or default_value
    if "/" not in candidate:
        return candidate
    path = Path(candidate)
    if not path.is_absolute():
        path = (base_dir / path).absolute()
    return str(path)


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
    service_python_bin: str
    comfyui_root_dir: Path
    comfyui_python_bin: str
    comfyui_host: str
    comfyui_port: int
    comfyui_input_dir: Path
    comfyui_output_dir: Path
    comfyui_workflow_template: Path
    comfyui_health_timeout_seconds: float
    comfyui_request_timeout_seconds: float
    comfyui_task_timeout_seconds: float
    comfyui_history_poll_interval_seconds: float
    comfyui_ws_receive_timeout_seconds: float
    comfyui_ready_on_startup: bool
    comfyui_required_model_paths: tuple[Path, ...]
    allowed_sizes: tuple[str, ...]
    default_size: str
    max_input_image_bytes: int
    video_length: int
    video_fps: int
    negative_prompt: str

    def ensure_directories(self) -> None:
        for path in (
            self.storage_dir,
            self.logs_dir,
            self.outputs_dir,
            self.third_party_dir,
            self.comfyui_input_dir,
            self.comfyui_output_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def comfyui_base_url(self) -> str:
        return f"http://{self.comfyui_host}:{self.comfyui_port}"

    @property
    def comfyui_ws_url(self) -> str:
        return f"ws://{self.comfyui_host}:{self.comfyui_port}/ws"


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
    db_path = _resolve_path(service_root, os.getenv("WAN_DB_PATH"), Path("storage/tasks.db"))

    comfyui_root_dir = _resolve_path(
        service_root,
        os.getenv("WAN_COMFYUI_DIR"),
        Path("third_party/ComfyUI"),
    )
    comfyui_input_dir = _resolve_path(
        service_root,
        os.getenv("WAN_COMFYUI_INPUT_DIR"),
        Path("storage/comfyui_input"),
    )
    comfyui_output_dir = _resolve_path(
        service_root,
        os.getenv("WAN_COMFYUI_OUTPUT_DIR"),
        Path("storage/comfyui_output"),
    )
    comfyui_workflow_template = _resolve_path(
        service_root,
        os.getenv("WAN_COMFYUI_WORKFLOW_TEMPLATE"),
        Path("workflows/wan22_i2v_a14b_lowvram_template.json"),
    )

    allowed_sizes = _parse_allowed_sizes(os.getenv("WAN_ALLOWED_SIZES"))
    default_size = (os.getenv("WAN_DEFAULT_SIZE") or DEFAULT_SIZE).strip() or DEFAULT_SIZE
    if default_size not in allowed_sizes:
        default_size = allowed_sizes[0]

    required_model_paths = tuple(
        (comfyui_root_dir / relative_path).resolve()
        for relative_path in COMFYUI_REQUIRED_MODEL_RELATIVE_PATHS
    )

    return Settings(
        service_root=service_root,
        service_host=(os.getenv("WAN_SERVICE_HOST") or "0.0.0.0").strip() or "0.0.0.0",
        service_port=int(os.getenv("WAN_SERVICE_PORT") or "8000"),
        db_path=db_path,
        logs_dir=logs_dir,
        outputs_dir=outputs_dir,
        storage_dir=storage_dir,
        third_party_dir=third_party_dir,
        service_python_bin=_resolve_exec_or_path(
            service_root,
            os.getenv("WAN_SERVICE_PYTHON_BIN"),
            ".venv/bin/python",
        ),
        comfyui_root_dir=comfyui_root_dir,
        comfyui_python_bin=_resolve_exec_or_path(
            service_root,
            os.getenv("WAN_COMFYUI_PYTHON_BIN"),
            ".comfyui-venv/bin/python",
        ),
        comfyui_host=(os.getenv("WAN_COMFYUI_HOST") or "127.0.0.1").strip() or "127.0.0.1",
        comfyui_port=int(os.getenv("WAN_COMFYUI_PORT") or "8188"),
        comfyui_input_dir=comfyui_input_dir,
        comfyui_output_dir=comfyui_output_dir,
        comfyui_workflow_template=comfyui_workflow_template,
        comfyui_health_timeout_seconds=_parse_optional_float(
            os.getenv("WAN_COMFYUI_HEALTH_TIMEOUT_SECONDS")
        )
        or 5.0,
        comfyui_request_timeout_seconds=_parse_optional_float(
            os.getenv("WAN_COMFYUI_REQUEST_TIMEOUT_SECONDS")
        )
        or 60.0,
        comfyui_task_timeout_seconds=_parse_optional_float(
            os.getenv("WAN_COMFYUI_TASK_TIMEOUT_SECONDS")
        )
        or 7200.0,
        comfyui_history_poll_interval_seconds=_parse_optional_float(
            os.getenv("WAN_COMFYUI_HISTORY_POLL_INTERVAL_SECONDS")
        )
        or 2.0,
        comfyui_ws_receive_timeout_seconds=_parse_optional_float(
            os.getenv("WAN_COMFYUI_WS_RECEIVE_TIMEOUT_SECONDS")
        )
        or 5.0,
        comfyui_ready_on_startup=_parse_env_bool(
            os.getenv("WAN_COMFYUI_REQUIRE_READY_ON_STARTUP"),
            False,
        ),
        comfyui_required_model_paths=required_model_paths,
        allowed_sizes=allowed_sizes,
        default_size=default_size,
        max_input_image_bytes=int(
            os.getenv("WAN_MAX_INPUT_IMAGE_BYTES") or DEFAULT_MAX_INPUT_IMAGE_BYTES
        ),
        video_length=_parse_optional_int(os.getenv("WAN_VIDEO_LENGTH")) or DEFAULT_VIDEO_LENGTH,
        video_fps=_parse_optional_int(os.getenv("WAN_VIDEO_FPS")) or DEFAULT_VIDEO_FPS,
        negative_prompt=(
            os.getenv("WAN_NEGATIVE_PROMPT") or DEFAULT_NEGATIVE_PROMPT
        ).strip()
        or DEFAULT_NEGATIVE_PROMPT,
    )
