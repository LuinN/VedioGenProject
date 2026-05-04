from __future__ import annotations

import asyncio
from pathlib import Path

from app.progress import TaskProgressState
from app.repository import TaskRecord
from app.task_backend import TaskBackendEvent, TaskExecutionResult
from app.task_runner import TaskRunner


class SuccessfulBackend:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def run_task(self, task: TaskRecord, event_callback=None) -> TaskExecutionResult:
        Path(task.log_path).write_text("worker log", encoding="utf-8")
        if event_callback is not None:
            event_callback(
                TaskBackendEvent(
                    progress=TaskProgressState(
                        status_message="queued",
                        progress_current=None,
                        progress_total=None,
                        progress_percent=None,
                    ),
                    backend_prompt_id="prompt-42",
                )
            )
            event_callback(
                TaskBackendEvent(
                    progress=TaskProgressState(
                        status_message="sampling",
                        progress_current=10,
                        progress_total=20,
                        progress_percent=50,
                    ),
                    backend_prompt_id="prompt-42",
                )
            )
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("video-bytes", encoding="utf-8")
        return TaskExecutionResult(
            success=True,
            output_path=str(self.output_path),
            error_message=None,
            backend_prompt_id="prompt-42",
        )


class FailedBackend:
    def run_task(self, task: TaskRecord, event_callback=None) -> TaskExecutionResult:
        Path(task.log_path).write_text("worker log", encoding="utf-8")
        return TaskExecutionResult(
            success=False,
            output_path=None,
            error_message="CUDA out of memory",
            failure_code="backend_oom",
            backend_prompt_id="prompt-oom",
        )


def test_task_runner_marks_success(repository, service_env: dict[str, Path]) -> None:
    task = repository.create_task(
        task_id="task-success",
        mode="i2v",
        prompt="success prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-success.log"),
        backend="comfyui_native",
    )
    output_path = service_env["outputs_dir"] / task.task_id / "result.mp4"
    runner = TaskRunner(repository, SuccessfulBackend(output_path))

    async def exercise() -> None:
        await runner.start()
        await runner.enqueue(task.task_id)
        await asyncio.wait_for(runner.join(), timeout=2)
        await runner.stop()

    asyncio.run(exercise())

    stored = repository.get_task(task.task_id)
    assert stored is not None
    assert stored.status == "succeeded"
    assert stored.output_path == str(output_path)
    assert stored.backend_prompt_id == "prompt-42"
    assert stored.status_message == "finished"
    assert stored.progress_percent == 100


def test_task_runner_marks_failure(repository, service_env: dict[str, Path]) -> None:
    task = repository.create_task(
        task_id="task-failure",
        mode="i2v",
        prompt="failure prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-failure.log"),
        backend="comfyui_native",
    )
    runner = TaskRunner(repository, FailedBackend())

    async def exercise() -> None:
        await runner.start()
        await runner.enqueue(task.task_id)
        await asyncio.wait_for(runner.join(), timeout=2)
        await runner.stop()

    asyncio.run(exercise())

    stored = repository.get_task(task.task_id)
    assert stored is not None
    assert stored.status == "failed"
    assert stored.output_path is None
    assert stored.error_message == "CUDA out of memory"
    assert stored.failure_code == "backend_oom"
    assert stored.backend_prompt_id == "prompt-oom"
