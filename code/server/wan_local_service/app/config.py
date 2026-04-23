from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SERVICE_NAME = "wan-local-service"
API_MODE_T2V = "t2v"
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
        python_bin=os.getenv("WAN_PYTHON_BIN") or sys.executable,
        allowed_sizes=allowed_sizes,
        default_size=default_size,
    )
