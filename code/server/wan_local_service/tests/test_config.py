from __future__ import annotations

import sys
from pathlib import Path

from app.config import load_settings


def test_load_settings_prefers_running_interpreter_for_inference(
    service_env: dict[str, Path],
    monkeypatch,
) -> None:
    monkeypatch.setenv("WAN_PYTHON_BIN", "/tmp/incorrect-global-python")

    settings = load_settings()

    assert settings.python_bin == sys.executable


def test_load_settings_uses_conservative_defaults_for_low_memory_profile(
    service_env: dict[str, Path],
) -> None:
    settings = load_settings()

    assert settings.low_memory_profile is False
    assert settings.frame_num is None
    assert settings.sample_steps is None
    assert settings.runtime_memory_guard_enabled is False


def test_load_settings_can_enable_low_memory_profile(
    service_env: dict[str, Path],
    monkeypatch,
) -> None:
    monkeypatch.setenv("WAN_LOW_MEMORY_PROFILE", "1")
    monkeypatch.setenv("WAN_ENFORCE_RUNTIME_MEMORY_GUARD", "1")

    settings = load_settings()

    assert settings.low_memory_profile is True
    assert settings.frame_num == 17
    assert settings.sample_steps == 20
    assert settings.runtime_memory_guard_enabled is True
