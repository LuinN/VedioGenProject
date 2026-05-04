from __future__ import annotations

from pathlib import Path

from app.comfyui_backend import ComfyUiNativeBackend
from app.comfyui_manager import ComfyUiManager
from app.config import load_settings
from app.task_backend import TaskBackendEvent


def _make_task(repository, service_env: dict[str, Path], *, task_id: str = "task-integration"):
    input_image = service_env["outputs_dir"] / task_id / "input_image.png"
    input_image.parent.mkdir(parents=True, exist_ok=True)
    input_image.write_bytes(b"\x89PNG\r\n\x1a\nfake-png")
    return repository.create_task(
        task_id=task_id,
        mode="i2v",
        prompt="a fantasy warrior stands still",
        size="832*480",
        log_path=str(service_env["logs_dir"] / f"{task_id}.log"),
        input_image_path=str(input_image.resolve()),
        backend="comfyui_native",
    )


def test_comfyui_backend_success_path(
    repository,
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    server = install_fake_comfyui("success")
    settings = load_settings()
    backend = ComfyUiNativeBackend(settings, ComfyUiManager(settings))
    task = _make_task(repository, service_env, task_id="task-success")

    events: list[TaskBackendEvent] = []
    result = backend.run_task(task, event_callback=events.append)

    assert server.prompt_calls
    submitted_prompt = server.prompt_calls[-1]["prompt"]
    assert submitted_prompt["97"]["inputs"]["image"].endswith(".png")
    assert submitted_prompt["93"]["inputs"]["text"] == task.prompt
    assert submitted_prompt["108"]["inputs"]["filename_prefix"] == task.task_id
    assert result.success is True
    assert result.output_path is not None
    assert Path(result.output_path).exists()
    assert events[0].progress.status_message == "uploading image"
    assert any(event.progress.status_message == "queued" for event in events)
    assert any(event.progress.status_message == "sampling" for event in events)
    assert any(event.progress.status_message == "saving video" for event in events)
    assert result.backend_prompt_id == "prompt-1"


def test_comfyui_backend_falls_back_to_history_when_websocket_closes(
    repository,
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("history_fallback_success")
    settings = load_settings()
    backend = ComfyUiNativeBackend(settings, ComfyUiManager(settings))
    task = _make_task(repository, service_env, task_id="task-history")

    events: list[TaskBackendEvent] = []
    result = backend.run_task(task, event_callback=events.append)

    assert result.success is True
    assert result.output_path is not None
    assert Path(task.log_path).read_text(encoding="utf-8").find("history fallback was used") >= 0


def test_comfyui_backend_maps_oom_failure_code(
    repository,
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("oom_failure")
    settings = load_settings()
    backend = ComfyUiNativeBackend(settings, ComfyUiManager(settings))
    task = _make_task(repository, service_env, task_id="task-oom")

    result = backend.run_task(task)

    assert result.success is False
    assert result.failure_code == "backend_oom"
    assert "out of memory" in (result.error_message or "").lower()


def test_comfyui_backend_reports_missing_output_file(
    repository,
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("output_missing")
    settings = load_settings()
    backend = ComfyUiNativeBackend(settings, ComfyUiManager(settings))
    task = _make_task(repository, service_env, task_id="task-missing-output")

    result = backend.run_task(task)

    assert result.success is False
    assert result.failure_code == "backend_output_missing"


def test_comfyui_backend_maps_prompt_validation_failures(
    repository,
    service_env: dict[str, Path],
    install_fake_comfyui,
) -> None:
    install_fake_comfyui("validation_error")
    settings = load_settings()
    backend = ComfyUiNativeBackend(settings, ComfyUiManager(settings))
    task = _make_task(repository, service_env, task_id="task-validation")

    result = backend.run_task(task)

    assert result.success is False
    assert result.failure_code == "backend_validation_error"
