from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    existing_columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
    )


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL,
                prompt TEXT NOT NULL,
                size TEXT NOT NULL,
                status TEXT NOT NULL,
                create_time TEXT NOT NULL,
                update_time TEXT NOT NULL,
                output_path TEXT NULL,
                input_image_path TEXT NULL,
                error_message TEXT NULL,
                log_path TEXT NOT NULL,
                status_message TEXT NULL,
                progress_current INTEGER NULL,
                progress_total INTEGER NULL,
                progress_percent INTEGER NULL
            )
            """
        )
        _ensure_column(connection, "tasks", "input_image_path", "TEXT NULL")
        _ensure_column(connection, "tasks", "status_message", "TEXT NULL")
        _ensure_column(connection, "tasks", "progress_current", "INTEGER NULL")
        _ensure_column(connection, "tasks", "progress_total", "INTEGER NULL")
        _ensure_column(connection, "tasks", "progress_percent", "INTEGER NULL")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_create_time
            ON tasks(create_time DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tasks_status
            ON tasks(status)
            """
        )
        connection.commit()
