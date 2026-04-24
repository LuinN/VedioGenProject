from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from .config import (
    RESTARTED_PENDING_MESSAGE,
    RESTARTED_RUNNING_MESSAGE,
    TASK_OUTPUT_FILENAME,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
)
from .progress import TaskProgressState, merge_progress_states, progress_from_log_line
from .repository import TaskRecord, TaskRepository


@dataclass(slots=True)
class TaskRuntimeSnapshot:
    output_exists: bool
    status_message: str | None
    progress_current: int | None
    progress_total: int | None
    progress_percent: int | None


@dataclass(slots=True)
class RecoverySummary:
    recovered_succeeded: int = 0
    recovered_pending_failed: int = 0
    recovered_running_failed: int = 0


def expected_output_path(outputs_dir: Path, task_id: str) -> Path:
    return (outputs_dir / task_id / TASK_OUTPUT_FILENAME).resolve()


def reconcile_task_completion(
    repository: TaskRepository,
    outputs_dir: Path,
    task: TaskRecord,
) -> TaskRecord:
    output_path = expected_output_path(outputs_dir, task.task_id)
    if not output_path.exists():
        return task
    output_path_text = str(output_path)
    if (
        task.status == TASK_STATUS_SUCCEEDED
        and task.output_path == output_path_text
    ):
        return task
    repository.mark_task_succeeded(task.task_id, output_path_text)
    refreshed = repository.get_task(task.task_id)
    return refreshed or task


def recover_interrupted_tasks(
    repository: TaskRepository,
    outputs_dir: Path,
) -> RecoverySummary:
    summary = RecoverySummary()
    interrupted_tasks = repository.list_tasks_by_statuses(
        (TASK_STATUS_PENDING, TASK_STATUS_RUNNING)
    )
    for task in interrupted_tasks:
        output_path = expected_output_path(outputs_dir, task.task_id)
        if output_path.exists():
            repository.mark_task_succeeded(task.task_id, str(output_path))
            summary.recovered_succeeded += 1
            continue
        if task.status == TASK_STATUS_PENDING:
            repository.mark_task_failed(task.task_id, RESTARTED_PENDING_MESSAGE)
            summary.recovered_pending_failed += 1
            continue
        repository.mark_task_failed(task.task_id, RESTARTED_RUNNING_MESSAGE)
        summary.recovered_running_failed += 1
    return summary


def build_task_runtime_snapshot(
    log_path: str | Path,
    *,
    output_path: str | None = None,
    expected_output: Path | None = None,
) -> TaskRuntimeSnapshot:
    resolved_output = False
    if output_path:
        resolved_output = Path(output_path).exists()
    if not resolved_output and expected_output is not None:
        resolved_output = expected_output.exists()

    path = Path(log_path)
    if not path.exists():
        return TaskRuntimeSnapshot(
            output_exists=resolved_output,
            status_message="output available" if resolved_output else None,
            progress_current=None,
            progress_total=None,
            progress_percent=100 if resolved_output else None,
        )

    progress_state = TaskProgressState()

    try:
        with path.open("r", encoding="utf-8") as log_file:
            for raw_line in log_file:
                progress_state = progress_from_log_line(progress_state, raw_line)
    except OSError:
        pass

    if resolved_output and progress_state.progress_percent is None:
        progress_state.progress_percent = 100
    if resolved_output and progress_state.status_message is None:
        progress_state.status_message = "output available"

    return TaskRuntimeSnapshot(
        output_exists=resolved_output,
        status_message=progress_state.status_message,
        progress_current=progress_state.progress_current,
        progress_total=progress_state.progress_total,
        progress_percent=progress_state.progress_percent,
    )


def build_task_progress_snapshot(
    task: TaskRecord,
    *,
    expected_output: Path | None = None,
) -> TaskRuntimeSnapshot:
    stored_state = TaskProgressState(
        status_message=task.status_message,
        progress_current=task.progress_current,
        progress_total=task.progress_total,
        progress_percent=task.progress_percent,
    )
    if any(
        value is not None
        for value in (
            stored_state.status_message,
            stored_state.progress_current,
            stored_state.progress_total,
            stored_state.progress_percent,
        )
    ):
        resolved_output = False
        if task.output_path:
            resolved_output = Path(task.output_path).exists()
        if not resolved_output and expected_output is not None:
            resolved_output = expected_output.exists()
        fallback = build_task_runtime_snapshot(
            task.log_path,
            output_path=task.output_path,
            expected_output=expected_output,
        )
        merged = merge_progress_states(
            TaskProgressState(
                status_message=fallback.status_message,
                progress_current=fallback.progress_current,
                progress_total=fallback.progress_total,
                progress_percent=fallback.progress_percent,
            ),
            stored_state,
        )
        if resolved_output and merged.progress_percent is None:
            merged.progress_percent = 100
        if resolved_output and merged.status_message is None:
            merged.status_message = "output available"
        return TaskRuntimeSnapshot(
            output_exists=resolved_output or fallback.output_exists,
            status_message=merged.status_message,
            progress_current=merged.progress_current,
            progress_total=merged.progress_total,
            progress_percent=merged.progress_percent,
        )

    return build_task_runtime_snapshot(
        task.log_path,
        output_path=task.output_path,
        expected_output=expected_output,
    )
