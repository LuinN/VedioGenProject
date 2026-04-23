from __future__ import annotations

import asyncio
from pathlib import Path

from app.repository import TaskRecord
from app.task_runner import TaskRunner
from app.wan_runner import WanExecutionResult


class SuccessfulWanRunner:
    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path

    def run_task(self, task: TaskRecord) -> WanExecutionResult:
        Path(task.log_path).write_text("worker log", encoding="utf-8")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text("video-bytes", encoding="utf-8")
        return WanExecutionResult(True, str(self.output_path), None)


class FailedWanRunner:
    def run_task(self, task: TaskRecord) -> WanExecutionResult:
        Path(task.log_path).write_text("worker log", encoding="utf-8")
        return WanExecutionResult(False, None, "simulated wan failure")


def test_task_runner_marks_success(repository, service_env: dict[str, Path]) -> None:
    task = repository.create_task(
        task_id="task-success",
        mode="t2v",
        prompt="success prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-success.log"),
    )
    output_path = service_env["outputs_dir"] / task.task_id / "result.mp4"
    runner = TaskRunner(repository, SuccessfulWanRunner(output_path))

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
    assert stored.error_message is None


def test_task_runner_marks_failure(repository, service_env: dict[str, Path]) -> None:
    task = repository.create_task(
        task_id="task-failure",
        mode="t2v",
        prompt="failure prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-failure.log"),
    )
    runner = TaskRunner(repository, FailedWanRunner())

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
    assert stored.error_message == "simulated wan failure"
