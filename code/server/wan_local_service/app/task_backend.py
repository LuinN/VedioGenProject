from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .progress import TaskProgressState
from .repository import TaskRecord


@dataclass(slots=True)
class TaskBackendEvent:
    progress: TaskProgressState
    backend_prompt_id: str | None = None


@dataclass(slots=True)
class TaskExecutionResult:
    success: bool
    output_path: str | None
    error_message: str | None
    failure_code: str | None = None
    backend_prompt_id: str | None = None


TaskBackendCallback = Callable[[TaskBackendEvent], None]


class TaskBackend(Protocol):
    def run_task(
        self,
        task: TaskRecord,
        event_callback: TaskBackendCallback | None = None,
    ) -> TaskExecutionResult:
        ...
