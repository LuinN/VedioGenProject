from __future__ import annotations

from pathlib import Path

import pytest

from app.config import load_settings
from app.wan_runner import WanRunner


def test_wan_runner_returns_specific_failure_summary(
    repository,
    service_env: dict[str, Path],
) -> None:
    service_env["generate_py"].write_text(
        """
import sys

print("Traceback (most recent call last):")
print("  File \\"fake.py\\", line 1, in <module>")
print("ModuleNotFoundError: No module named 'einops'")
sys.exit(1)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-generate-failure",
        mode="t2v",
        prompt="failure prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-generate-failure.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is False
    assert result.output_path is None
    assert (
        result.error_message
        == "ModuleNotFoundError: No module named 'einops' (generate.py exit code 1)"
    )


def test_wan_runner_reports_success_and_output_path(
    repository,
    service_env: dict[str, Path],
) -> None:
    service_env["generate_py"].write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
save_file = pathlib.Path(args[args.index("--save_file") + 1])
save_file.parent.mkdir(parents=True, exist_ok=True)
save_file.write_text("video-bytes", encoding="utf-8")
print("generation finished")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-generate-success",
        mode="t2v",
        prompt="success prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-generate-success.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is True
    assert result.error_message is None
    assert result.output_path is not None
    assert Path(result.output_path).exists()


def test_wan_runner_uses_low_memory_generation_profile_in_command_log(
    repository,
    service_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAN_LOW_MEMORY_PROFILE", "1")
    service_env["generate_py"].write_text(
        """
import pathlib
import sys

args = sys.argv[1:]
save_file = pathlib.Path(args[args.index("--save_file") + 1])
save_file.parent.mkdir(parents=True, exist_ok=True)
save_file.write_text("video-bytes", encoding="utf-8")
print("generation finished")
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-low-memory-profile",
        mode="t2v",
        prompt="profile prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-low-memory-profile.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is True
    log_text = Path(task.log_path).read_text(encoding="utf-8")
    assert "--frame_num 17" in log_text
    assert "--sample_steps 20" in log_text
    assert "--offload_model True" in log_text
    assert "--t5_cpu" in log_text
    assert "--convert_model_dtype" in log_text


def test_wan_runner_fails_early_when_runtime_memory_guard_triggers(
    repository,
    service_env: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAN_ENFORCE_RUNTIME_MEMORY_GUARD", "1")
    monkeypatch.setenv("WAN_MIN_MEM_AVAILABLE_GB", "1024")
    monkeypatch.setenv("WAN_MIN_SWAP_AVAILABLE_GB", "1024")
    service_env["generate_py"].write_text(
        "print('should not run')\n",
        encoding="utf-8",
    )

    settings = load_settings()
    task = repository.create_task(
        task_id="task-low-memory-guard",
        mode="t2v",
        prompt="guard prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-low-memory-guard.log"),
    )

    result = WanRunner(settings).run_task(task)

    assert result.success is False
    assert result.output_path is None
    assert result.error_message is not None
    assert "insufficient memory headroom before generation" in result.error_message
