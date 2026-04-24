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
    error_message: str | None
    log_path: str


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
        error_message=row["error_message"],
        log_path=row["log_path"],
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
                    error_message,
                    log_path
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    None,
                    log_path,
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
            SET status = ?, update_time = ?, output_path = NULL, error_message = NULL
            WHERE task_id = ?
            """,
            (TASK_STATUS_RUNNING, utcnow_text(), task_id),
        )

    def mark_task_succeeded(self, task_id: str, output_path: str) -> None:
        self._execute(
            """
            UPDATE tasks
            SET status = ?, update_time = ?, output_path = ?, error_message = NULL
            WHERE task_id = ?
            """,
            (TASK_STATUS_SUCCEEDED, utcnow_text(), output_path, task_id),
        )

    def mark_task_failed(self, task_id: str, error_message: str) -> None:
        self._execute(
            """
            UPDATE tasks
            SET status = ?, update_time = ?, output_path = NULL, error_message = ?
            WHERE task_id = ?
            """,
            (TASK_STATUS_FAILED, utcnow_text(), error_message, task_id),
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
