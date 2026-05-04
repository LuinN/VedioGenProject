from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import (
    RESTARTED_PENDING_MESSAGE,
    RESTARTED_RUNNING_MESSAGE,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_SUCCEEDED,
)
from .db import connect
from .progress import TaskProgressState


def utcnow_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    mode: str
    prompt: str
    size: str
    status: str
    create_time: str
    update_time: str
    output_path: str | None
    input_image_path: str | None
    error_message: str | None
    backend: str | None
    backend_prompt_id: str | None
    failure_code: str | None
    log_path: str
    status_message: str | None
    progress_current: int | None
    progress_total: int | None
    progress_percent: int | None


def _row_to_task(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        mode=row["mode"],
        prompt=row["prompt"],
        size=row["size"],
        status=row["status"],
        create_time=row["create_time"],
        update_time=row["update_time"],
        output_path=row["output_path"],
        input_image_path=row["input_image_path"],
        error_message=row["error_message"],
        backend=row["backend"],
        backend_prompt_id=row["backend_prompt_id"],
        failure_code=row["failure_code"],
        log_path=row["log_path"],
        status_message=row["status_message"],
        progress_current=row["progress_current"],
        progress_total=row["progress_total"],
        progress_percent=row["progress_percent"],
    )


class TaskRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def create_task(
        self,
        *,
        task_id: str,
        mode: str,
        prompt: str,
        size: str,
        log_path: str,
        input_image_path: str | None = None,
        backend: str | None = None,
    ) -> TaskRecord:
        timestamp = utcnow_text()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id,
                    mode,
                    prompt,
                    size,
                    status,
                    create_time,
                    update_time,
                    output_path,
                    input_image_path,
                    error_message,
                    backend,
                    backend_prompt_id,
                    failure_code,
                    log_path,
                    status_message,
                    progress_current,
                    progress_total,
                    progress_percent
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    mode,
                    prompt,
                    size,
                    TASK_STATUS_PENDING,
                    timestamp,
                    timestamp,
                    None,
                    input_image_path,
                    None,
                    backend,
                    None,
                    None,
                    log_path,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            connection.commit()
        task = self.get_task(task_id)
        if task is None:
            raise RuntimeError(f"failed to create task {task_id}")
        return task

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return _row_to_task(row) if row is not None else None

    def delete_task(self, task_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM tasks WHERE task_id = ?",
                (task_id,),
            )
            connection.commit()
        return cursor.rowcount > 0

    def list_tasks(self, limit: int) -> list[TaskRecord]:
        return self._list(
            """
            SELECT * FROM tasks
            ORDER BY create_time DESC
            LIMIT ?
            """,
            (limit,),
        )

    def list_results(self, limit: int) -> list[TaskRecord]:
        return self._list(
            """
            SELECT * FROM tasks
            WHERE status = ?
            ORDER BY create_time DESC
            LIMIT ?
            """,
            (TASK_STATUS_SUCCEEDED, limit),
        )

    def list_tasks_by_statuses(self, statuses: Iterable[str]) -> list[TaskRecord]:
        normalized_statuses = tuple(statuses)
        if not normalized_statuses:
            return []
        placeholders = ", ".join("?" for _ in normalized_statuses)
        return self._list(
            f"""
            SELECT * FROM tasks
            WHERE status IN ({placeholders})
            ORDER BY create_time DESC
            """,
            normalized_statuses,
        )

    def count_tasks(self) -> int:
        return self._count("SELECT COUNT(*) FROM tasks")

    def count_results(self) -> int:
        return self._count(
            "SELECT COUNT(*) FROM tasks WHERE status = ?",
            (TASK_STATUS_SUCCEEDED,),
        )

    def mark_task_running(self, task_id: str) -> None:
        self._execute(
            """
            UPDATE tasks
            SET
                status = ?,
                update_time = ?,
                output_path = NULL,
                error_message = NULL,
                failure_code = NULL,
                status_message = ?,
                progress_current = NULL,
                progress_total = NULL,
                progress_percent = NULL
            WHERE task_id = ?
            """,
            (TASK_STATUS_RUNNING, utcnow_text(), "starting", task_id),
        )

    def mark_task_succeeded(
        self,
        task_id: str,
        output_path: str,
        *,
        backend_prompt_id: str | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE tasks
            SET
                status = ?,
                update_time = ?,
                output_path = ?,
                error_message = NULL,
                failure_code = NULL,
                backend_prompt_id = COALESCE(?, backend_prompt_id),
                status_message = ?,
                progress_percent = ?,
                progress_current = COALESCE(progress_total, progress_current)
            WHERE task_id = ?
            """,
            (
                TASK_STATUS_SUCCEEDED,
                utcnow_text(),
                output_path,
                backend_prompt_id,
                "finished",
                100,
                task_id,
            ),
        )

    def mark_task_failed(
        self,
        task_id: str,
        error_message: str,
        *,
        failure_code: str | None = None,
        backend_prompt_id: str | None = None,
    ) -> None:
        self._execute(
            """
            UPDATE tasks
            SET
                status = ?,
                update_time = ?,
                output_path = NULL,
                error_message = ?,
                failure_code = ?,
                backend_prompt_id = COALESCE(?, backend_prompt_id)
            WHERE task_id = ?
            """,
            (
                TASK_STATUS_FAILED,
                utcnow_text(),
                error_message,
                failure_code,
                backend_prompt_id,
                task_id,
            ),
        )

    def update_task_progress(self, task_id: str, progress: TaskProgressState) -> None:
        self._execute(
            """
            UPDATE tasks
            SET
                update_time = ?,
                status_message = ?,
                progress_current = ?,
                progress_total = ?,
                progress_percent = ?
            WHERE task_id = ?
            """,
            (
                utcnow_text(),
                progress.status_message,
                progress.progress_current,
                progress.progress_total,
                progress.progress_percent,
                task_id,
            ),
        )

    def set_backend_prompt_id(self, task_id: str, backend_prompt_id: str) -> None:
        self._execute(
            """
            UPDATE tasks
            SET backend_prompt_id = ?, update_time = ?
            WHERE task_id = ?
            """,
            (backend_prompt_id, utcnow_text(), task_id),
        )

    def recover_interrupted_tasks(self) -> dict[str, int]:
        timestamp = utcnow_text()
        with self._connect() as connection:
            pending_count = connection.execute(
                """
                UPDATE tasks
                SET status = ?, update_time = ?, output_path = NULL, error_message = ?
                WHERE status = ?
                """,
                (
                    TASK_STATUS_FAILED,
                    timestamp,
                    RESTARTED_PENDING_MESSAGE,
                    TASK_STATUS_PENDING,
                ),
            ).rowcount
            running_count = connection.execute(
                """
                UPDATE tasks
                SET status = ?, update_time = ?, output_path = NULL, error_message = ?
                WHERE status = ?
                """,
                (
                    TASK_STATUS_FAILED,
                    timestamp,
                    RESTARTED_RUNNING_MESSAGE,
                    TASK_STATUS_RUNNING,
                ),
            ).rowcount
            connection.commit()
        return {"pending": pending_count, "running": running_count}

    def _list(self, query: str, params: Iterable[object]) -> list[TaskRecord]:
        with self._connect() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [_row_to_task(row) for row in rows]

    def _count(self, query: str, params: Iterable[object] = ()) -> int:
        with self._connect() as connection:
            value = connection.execute(query, tuple(params)).fetchone()[0]
        return int(value)

    def _execute(self, query: str, params: Iterable[object]) -> None:
        with self._connect() as connection:
            connection.execute(query, tuple(params))
            connection.commit()
