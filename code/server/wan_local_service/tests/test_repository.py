from __future__ import annotations

from pathlib import Path

from app.config import RESTARTED_PENDING_MESSAGE, RESTARTED_RUNNING_MESSAGE
from app.db import connect
from app.progress import TaskProgressState


def test_list_tasks_returns_newest_first(repository, service_env: dict[str, Path]) -> None:
    older = repository.create_task(
        task_id="task-older",
        mode="i2v",
        prompt="older prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-older.log"),
        backend="comfyui_native",
    )
    newer = repository.create_task(
        task_id="task-newer",
        mode="i2v",
        prompt="newer prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-newer.log"),
        backend="comfyui_native",
    )

    with connect(service_env["db_path"]) as connection:
        connection.execute(
            "UPDATE tasks SET create_time = ?, update_time = ? WHERE task_id = ?",
            ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", older.task_id),
        )
        connection.execute(
            "UPDATE tasks SET create_time = ?, update_time = ? WHERE task_id = ?",
            ("2026-01-02T00:00:00+00:00", "2026-01-02T00:00:00+00:00", newer.task_id),
        )
        connection.commit()

    tasks = repository.list_tasks(limit=10)
    assert [task.task_id for task in tasks] == ["task-newer", "task-older"]


def test_repository_persists_backend_prompt_and_failure_code(
    repository,
    service_env: dict[str, Path],
) -> None:
    task = repository.create_task(
        task_id="task-progress",
        mode="i2v",
        prompt="image prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-progress.log"),
        backend="comfyui_native",
    )

    repository.mark_task_running(task.task_id)
    repository.set_backend_prompt_id(task.task_id, "prompt-123")
    repository.update_task_progress(
        task.task_id,
        TaskProgressState(
            status_message="sampling",
            progress_current=3,
            progress_total=20,
            progress_percent=15,
        ),
    )
    repository.mark_task_failed(
        task.task_id,
        "CUDA out of memory",
        failure_code="backend_oom",
        backend_prompt_id="prompt-123",
    )

    stored = repository.get_task(task.task_id)
    assert stored is not None
    assert stored.backend == "comfyui_native"
    assert stored.backend_prompt_id == "prompt-123"
    assert stored.failure_code == "backend_oom"
    assert stored.status_message == "sampling"
    assert stored.progress_percent == 15


def test_recover_interrupted_tasks_marks_pending_and_running_failed(
    repository,
    service_env: dict[str, Path],
) -> None:
    pending_task = repository.create_task(
        task_id="task-pending",
        mode="i2v",
        prompt="pending prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-pending.log"),
        backend="comfyui_native",
    )
    running_task = repository.create_task(
        task_id="task-running",
        mode="i2v",
        prompt="running prompt",
        size="832*480",
        log_path=str(service_env["logs_dir"] / "task-running.log"),
        backend="comfyui_native",
    )
    repository.mark_task_running(running_task.task_id)

    counts = repository.recover_interrupted_tasks()

    assert counts == {"pending": 1, "running": 1}
    recovered_pending = repository.get_task(pending_task.task_id)
    recovered_running = repository.get_task(running_task.task_id)
    assert recovered_pending is not None
    assert recovered_running is not None
    assert recovered_pending.status == "failed"
    assert recovered_pending.error_message == RESTARTED_PENDING_MESSAGE
    assert recovered_running.status == "failed"
    assert recovered_running.error_message == RESTARTED_RUNNING_MESSAGE
