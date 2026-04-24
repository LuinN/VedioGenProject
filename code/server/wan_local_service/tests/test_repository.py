from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import RESTARTED_PENDING_MESSAGE, RESTARTED_RUNNING_MESSAGE
from app.db import connect
from app.progress import TaskProgressState


def test_list_tasks_returns_newest_first(repository, service_env: dict[str, Path]) -> None:
    older = repository.create_task(
        task_id="task-older",
        mode="t2v",
        prompt="older prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-older.log"),
    )
    newer = repository.create_task(
        task_id="task-newer",
        mode="t2v",
        prompt="newer prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-newer.log"),
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


def test_recover_interrupted_tasks_marks_pending_and_running_failed(
    repository,
    service_env: dict[str, Path],
) -> None:
    pending_task = repository.create_task(
        task_id="task-pending",
        mode="t2v",
        prompt="pending prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-pending.log"),
    )
    running_task = repository.create_task(
        task_id="task-running",
        mode="t2v",
        prompt="running prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-running.log"),
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
    assert recovered_pending.output_path is None
    assert recovered_pending.log_path == pending_task.log_path
    assert recovered_running.status == "failed"
    assert recovered_running.error_message == RESTARTED_RUNNING_MESSAGE
    assert recovered_running.output_path is None
    assert recovered_running.log_path == running_task.log_path


def test_update_task_progress_persists_runtime_fields(
    repository,
    service_env: dict[str, Path],
) -> None:
    task = repository.create_task(
        task_id="task-progress",
        mode="t2v",
        prompt="progress prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-progress.log"),
    )

    repository.mark_task_running(task.task_id)
    repository.update_task_progress(
        task.task_id,
        TaskProgressState(
            status_message="sampling",
            progress_current=21,
            progress_total=50,
            progress_percent=42,
        ),
    )

    stored = repository.get_task(task.task_id)
    assert stored is not None
    assert stored.status == "running"
    assert stored.status_message == "sampling"
    assert stored.progress_current == 21
    assert stored.progress_total == 50
    assert stored.progress_percent == 42


def test_create_task_persists_input_image_path(
    repository,
    service_env: dict[str, Path],
) -> None:
    input_image_path = service_env["outputs_dir"] / "task-image" / "input_image.png"
    input_image_path.parent.mkdir(parents=True, exist_ok=True)
    input_image_path.write_bytes(b"fake-png")

    task = repository.create_task(
        task_id="task-image",
        mode="i2v",
        prompt="image prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-image.log"),
        input_image_path=str(input_image_path.resolve()),
    )

    stored = repository.get_task(task.task_id)
    assert stored is not None
    assert stored.mode == "i2v"
    assert stored.input_image_path == str(input_image_path.resolve())


def test_delete_task_removes_row(repository, service_env: dict[str, Path]) -> None:
    task = repository.create_task(
        task_id="task-delete",
        mode="t2v",
        prompt="delete prompt",
        size="1280*704",
        log_path=str(service_env["logs_dir"] / "task-delete.log"),
    )

    deleted = repository.delete_task(task.task_id)

    assert deleted is True
    assert repository.get_task(task.task_id) is None
