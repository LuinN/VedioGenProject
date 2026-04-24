from __future__ import annotations

import re
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
from .repository import TaskRecord, TaskRepository


_PROGRESS_RE = re.compile(
    r"(?P<percent>\d{1,3})%\|.*?\|\s*(?P<current>\d+)/(?P<total>\d+)\s*\["
)


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

    status_message: str | None = "output available" if resolved_output else None
    progress_current: int | None = None
    progress_total: int | None = None
    progress_percent: int | None = 100 if resolved_output else None

    try:
        with path.open("r", encoding="utf-8") as log_file:
            for raw_line in log_file:
                line = raw_line.strip()
                if not line:
                    continue

                progress_match = _PROGRESS_RE.search(line)
                if progress_match is not None:
                    progress_current = int(progress_match.group("current"))
                    progress_total = int(progress_match.group("total"))
                    progress_percent = int(progress_match.group("percent"))
                    status_message = "sampling"
                    continue

                if "Creating WanTI2V pipeline." in line:
                    status_message = "creating pipeline"
                elif "Creating WanModel" in line or "loading " in line:
                    status_message = "loading checkpoints"
                elif "Generating video ..." in line:
                    status_message = "sampling"
                elif "Saving generated video to " in line:
                    status_message = "saving video"
                elif line == "generate.py exit code: 0" or "Finished." in line:
                    status_message = "finished"
                    progress_percent = 100
    except OSError:
        pass

    return TaskRuntimeSnapshot(
        output_exists=resolved_output,
        status_message=status_message,
        progress_current=progress_current,
        progress_total=progress_total,
        progress_percent=progress_percent,
    )
