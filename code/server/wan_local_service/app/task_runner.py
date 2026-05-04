from __future__ import annotations

import asyncio
import queue
import threading

from .repository import TaskRepository
from .task_backend import TaskBackend, TaskBackendEvent


_SENTINEL = object()


class TaskRunner:
    def __init__(self, repository: TaskRepository, backend: TaskBackend) -> None:
        self.repository = repository
        self.backend = backend
        self._queue: queue.Queue[str | object] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    async def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="wan-local-service-worker",
            daemon=True,
        )
        self._thread.start()

    async def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=1)
        self._thread = None

    async def enqueue(self, task_id: str) -> None:
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError("task runner has not been started")
        self._queue.put(task_id)

    async def join(self) -> None:
        while self._queue.unfinished_tasks > 0:
            await asyncio.sleep(0.01)

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL and self._stop_event.is_set():
                    return
                assert isinstance(item, str)
                self._process_task(item)
            finally:
                self._queue.task_done()

    def _process_task(self, task_id: str) -> None:
        task = self.repository.get_task(task_id)
        if task is None:
            return
        self.repository.mark_task_running(task_id)
        running_task = self.repository.get_task(task_id)
        if running_task is None:
            return
        try:
            result = self.backend.run_task(
                running_task,
                event_callback=lambda event: self._handle_backend_event(
                    task_id,
                    event,
                ),
            )
        except Exception as exc:  # pragma: no cover - defensive safety net
            self.repository.mark_task_failed(
                task_id,
                str(exc) or repr(exc),
                failure_code="backend_execution_error",
            )
            return

        if result.success and result.output_path is not None:
            self.repository.mark_task_succeeded(
                task_id,
                result.output_path,
                backend_prompt_id=result.backend_prompt_id,
            )
            return

        error_message = result.error_message or "Backend execution failed without details"
        self.repository.mark_task_failed(
            task_id,
            error_message,
            failure_code=result.failure_code,
            backend_prompt_id=result.backend_prompt_id,
        )

    def _handle_backend_event(self, task_id: str, event: TaskBackendEvent) -> None:
        if event.backend_prompt_id:
            self.repository.set_backend_prompt_id(task_id, event.backend_prompt_id)
        self.repository.update_task_progress(task_id, event.progress)
