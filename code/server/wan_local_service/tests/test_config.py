from __future__ import annotations

import sys
from pathlib import Path

from app.config import load_settings


def test_load_settings_uses_comfyui_14b_defaults(
    service_env: dict[str, Path],
) -> None:
    settings = load_settings()

    assert settings.allowed_sizes == ("832*480", "480*832")
    assert settings.default_size == "832*480"
    assert settings.video_length == 49
    assert settings.video_fps == 16
    assert settings.comfyui_workflow_template.name == "wan22_i2v_a14b_lowvram_template.json"
    assert settings.comfyui_required_model_paths
    assert all(path.is_absolute() for path in settings.comfyui_required_model_paths)
    assert settings.service_python_bin == sys.executable
    assert settings.comfyui_python_bin == sys.executable


def test_load_settings_can_override_comfyui_network_settings(
    service_env: dict[str, Path],
    monkeypatch,
) -> None:
    monkeypatch.setenv("WAN_COMFYUI_HOST", "0.0.0.0")
    monkeypatch.setenv("WAN_COMFYUI_PORT", "9001")
    monkeypatch.setenv("WAN_VIDEO_LENGTH", "65")
    monkeypatch.setenv("WAN_VIDEO_FPS", "24")

    settings = load_settings()

    assert settings.comfyui_host == "0.0.0.0"
    assert settings.comfyui_port == 9001
    assert settings.video_length == 65
    assert settings.video_fps == 24
