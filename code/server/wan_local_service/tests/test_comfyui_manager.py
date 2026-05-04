from __future__ import annotations

from pathlib import Path

from app.comfyui_manager import ComfyUiManager
from app.config import load_settings


def test_manager_reports_missing_model_files(service_env: dict[str, Path]) -> None:
    settings = load_settings()
    missing_model = settings.comfyui_required_model_paths[0]
    missing_model.unlink()

    status = ComfyUiManager(settings).get_status()

    assert status.backend == "comfyui_native"
    assert status.backend_ready is False
    assert status.model_ready is False
    assert str(missing_model) in (status.reason or "")
