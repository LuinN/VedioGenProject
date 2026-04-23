from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.db import init_db
from app.repository import TaskRepository


@pytest.fixture()
def service_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    storage_dir = tmp_path / "storage"
    logs_dir = tmp_path / "logs"
    outputs_dir = tmp_path / "outputs"
    third_party_dir = tmp_path / "third_party"
    repo_dir = third_party_dir / "Wan2.2"
    model_dir = third_party_dir / "Wan2.2-TI2V-5B"
    generate_py = repo_dir / "generate.py"

    for path in (storage_dir, logs_dir, outputs_dir, third_party_dir, repo_dir, model_dir):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("WAN_STORAGE_DIR", str(storage_dir))
    monkeypatch.setenv("WAN_LOG_DIR", str(logs_dir))
    monkeypatch.setenv("WAN_OUTPUT_DIR", str(outputs_dir))
    monkeypatch.setenv("WAN_THIRD_PARTY_DIR", str(third_party_dir))
    monkeypatch.setenv("WAN_REPO_DIR", str(repo_dir))
    monkeypatch.setenv("WAN_MODEL_DIR", str(model_dir))
    monkeypatch.setenv("WAN_GENERATE_PY", str(generate_py))
    monkeypatch.setenv("WAN_DB_PATH", str(storage_dir / "tasks.db"))
    monkeypatch.setenv("WAN_PYTHON_BIN", sys.executable)
    monkeypatch.setenv("WAN_ALLOWED_SIZES", "1280*704,704*1280")
    monkeypatch.setenv("WAN_DEFAULT_SIZE", "1280*704")
    return {
        "storage_dir": storage_dir,
        "logs_dir": logs_dir,
        "outputs_dir": outputs_dir,
        "third_party_dir": third_party_dir,
        "repo_dir": repo_dir,
        "model_dir": model_dir,
        "generate_py": generate_py,
        "db_path": storage_dir / "tasks.db",
    }


@pytest.fixture()
def repository(service_env: dict[str, Path]) -> TaskRepository:
    init_db(service_env["db_path"])
    return TaskRepository(service_env["db_path"])
