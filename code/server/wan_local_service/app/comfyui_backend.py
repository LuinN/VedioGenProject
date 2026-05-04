from __future__ import annotations

import json
import random
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from websocket import WebSocketConnectionClosedException, WebSocketTimeoutException, create_connection

from .comfyui_manager import ComfyUiManager
from .comfyui_workflow import (
    SAVE_VIDEO_NODE_ID,
    WorkflowOverrides,
    WorkflowTemplateError,
    instantiate_workflow,
    load_workflow_template,
    parse_size_token,
    workflow_to_api_prompt,
)
from .config import BACKEND_ID_COMFYUI_NATIVE, Settings, TASK_OUTPUT_FILENAME
from .progress import TaskProgressState
from .repository import TaskRecord
from .task_backend import TaskBackendEvent, TaskBackendCallback, TaskExecutionResult


@dataclass(slots=True)
class HistoryOutcome:
    terminal: bool
    success: bool = False
    error_message: str | None = None
    failure_code: str | None = None


class ComfyUiNativeBackend:
    def __init__(self, settings: Settings, manager: ComfyUiManager) -> None:
        self.settings = settings
        self.manager = manager

    def run_task(
        self,
        task: TaskRecord,
        event_callback: TaskBackendCallback | None = None,
    ) -> TaskExecutionResult:
        status = self.manager.get_status()
        if not status.backend_ready:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=status.reason or "ComfyUI backend is unavailable",
                failure_code="backend_unavailable",
            )

        if not task.input_image_path:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message="i2v task is missing input_image_path",
                failure_code="backend_validation_error",
            )

        input_image = Path(task.input_image_path)
        if not input_image.is_file():
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=f"input image not found: {input_image}",
                failure_code="backend_validation_error",
            )

        try:
            workflow_template = load_workflow_template(self.settings.comfyui_workflow_template)
            object_info = self.manager.fetch_object_info()
        except Exception as exc:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=str(exc) or repr(exc),
                failure_code="backend_unavailable",
            )

        uploaded_image_name = self._upload_image(task, input_image, event_callback)
        if uploaded_image_name is None:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message="failed to upload input image to ComfyUI",
                failure_code="backend_upload_failed",
            )

        width, height = parse_size_token(task.size)
        seed = random.randint(10**14, 10**15 - 1)
        workflow = instantiate_workflow(
            workflow_template,
            WorkflowOverrides(
                image_name=uploaded_image_name,
                prompt=task.prompt,
                negative_prompt=self.settings.negative_prompt,
                width=width,
                height=height,
                length=self.settings.video_length,
                fps=self.settings.video_fps,
                output_prefix=task.task_id,
                seed=seed,
            ),
        )

        try:
            prompt = workflow_to_api_prompt(workflow, object_info)
        except WorkflowTemplateError as exc:
            self._append_log(task.log_path, f"workflow conversion failed: {exc}")
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=str(exc),
                failure_code="backend_validation_error",
            )

        client_id = str(uuid4())
        prompt_id: str | None = None
        try:
            prompt_id = self._submit_prompt(task, prompt, client_id)
        except Exception as exc:
            error_text = str(exc) or repr(exc)
            failure_code = (
                "backend_validation_error"
                if "node_errors" in error_text or "validation" in error_text.lower()
                else "backend_execution_error"
            )
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=error_text,
                failure_code=failure_code,
            )

        self._emit_event(
            event_callback,
            task.log_path,
            "queued",
            backend_prompt_id=prompt_id,
        )

        wait_result = self._wait_for_completion(
            task,
            prompt_id,
            client_id,
            event_callback,
        )
        if not wait_result.success:
            wait_result.backend_prompt_id = prompt_id
            return wait_result

        output_path = self._collect_output_file(task.task_id)
        if output_path is None:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=f"ComfyUI finished but no mp4 was found for prefix '{task.task_id}'",
                failure_code="backend_output_missing",
                backend_prompt_id=prompt_id,
            )

        task_output_dir = (self.settings.outputs_dir / task.task_id).resolve()
        task_output_dir.mkdir(parents=True, exist_ok=True)
        final_output_path = (task_output_dir / TASK_OUTPUT_FILENAME).resolve()
        shutil.copy2(output_path, final_output_path)
        self._append_log(task.log_path, f"copied result to {final_output_path}")
        return TaskExecutionResult(
            success=True,
            output_path=str(final_output_path),
            error_message=None,
            backend_prompt_id=prompt_id,
        )

    def _upload_image(
        self,
        task: TaskRecord,
        input_image: Path,
        event_callback: TaskBackendCallback | None,
    ) -> str | None:
        self._emit_event(event_callback, task.log_path, "uploading image")
        try:
            with httpx.Client(
                base_url=self.settings.comfyui_base_url,
                timeout=self.settings.comfyui_request_timeout_seconds,
            ) as client:
                with input_image.open("rb") as image_file:
                    response = client.post(
                        "/upload/image",
                        files={
                            "image": (
                                input_image.name,
                                image_file,
                                "application/octet-stream",
                            ),
                        },
                    )
                response.raise_for_status()
        except Exception as exc:
            self._append_log(task.log_path, f"image upload failed: {type(exc).__name__}: {exc}")
            return None

        payload = response.json()
        if not isinstance(payload, dict) or "name" not in payload:
            self._append_log(task.log_path, f"unexpected upload response: {payload!r}")
            return None
        uploaded_name = str(payload["name"])
        subfolder = str(payload.get("subfolder") or "").strip().strip("/")
        final_name = f"{subfolder}/{uploaded_name}" if subfolder else uploaded_name
        self._append_log(task.log_path, f"uploaded image as {final_name}")
        return final_name

    def _submit_prompt(
        self,
        task: TaskRecord,
        prompt: dict[str, Any],
        client_id: str,
    ) -> str:
        payload = {
            "prompt": prompt,
            "client_id": client_id,
        }
        self._append_log(task.log_path, f"submitting prompt client_id={client_id}")
        with httpx.Client(
            base_url=self.settings.comfyui_base_url,
            timeout=self.settings.comfyui_request_timeout_seconds,
        ) as client:
            response = client.post("/prompt", json=payload)
            if response.is_error:
                raise RuntimeError(
                    f"ComfyUI /prompt HTTP {response.status_code}: {response.text}"
                )
            body = response.json()

        prompt_id = str(body.get("prompt_id") or "").strip()
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {body!r}")

        node_errors = body.get("node_errors") or {}
        if node_errors:
            raise RuntimeError(f"ComfyUI validation failed: node_errors={node_errors!r}")

        self._append_log(task.log_path, f"prompt queued prompt_id={prompt_id}")
        return prompt_id

    def _wait_for_completion(
        self,
        task: TaskRecord,
        prompt_id: str,
        client_id: str,
        event_callback: TaskBackendCallback | None,
    ) -> TaskExecutionResult:
        deadline = time.monotonic() + self.settings.comfyui_task_timeout_seconds
        ws_url = f"{self.settings.comfyui_ws_url}?clientId={client_id}"
        saw_ws_failure = False

        try:
            ws = create_connection(
                ws_url,
                timeout=self.settings.comfyui_ws_receive_timeout_seconds,
            )
        except Exception as exc:
            saw_ws_failure = True
            self._append_log(task.log_path, f"websocket unavailable, falling back to history: {exc}")
            ws = None

        try:
            while time.monotonic() < deadline:
                if ws is not None:
                    try:
                        message = ws.recv()
                    except WebSocketTimeoutException:
                        history = self._poll_history(task, prompt_id, event_callback)
                        if history.terminal:
                            return self._history_outcome_to_result(history, prompt_id)
                        continue
                    except WebSocketConnectionClosedException as exc:
                        saw_ws_failure = True
                        self._append_log(task.log_path, f"websocket closed: {exc}")
                        try:
                            ws.close()
                        except Exception:
                            pass
                        ws = None
                        history = self._poll_history(task, prompt_id, event_callback)
                        if history.terminal:
                            return self._history_outcome_to_result(history, prompt_id)
                        time.sleep(self.settings.comfyui_history_poll_interval_seconds)
                        continue
                    except Exception as exc:
                        saw_ws_failure = True
                        self._append_log(task.log_path, f"websocket failed: {exc}")
                        try:
                            ws.close()
                        except Exception:
                            pass
                        ws = None
                        history = self._poll_history(task, prompt_id, event_callback)
                        if history.terminal:
                            return self._history_outcome_to_result(history, prompt_id)
                        time.sleep(self.settings.comfyui_history_poll_interval_seconds)
                        continue

                    outcome = self._handle_ws_message(
                        task,
                        prompt_id,
                        message,
                        event_callback,
                    )
                    if outcome is not None:
                        return outcome
                    continue

                history = self._poll_history(task, prompt_id, event_callback)
                if history.terminal:
                    return self._history_outcome_to_result(history, prompt_id)
                time.sleep(self.settings.comfyui_history_poll_interval_seconds)

            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=f"ComfyUI task timed out after {self.settings.comfyui_task_timeout_seconds:.0f}s",
                failure_code="backend_timeout",
                backend_prompt_id=prompt_id,
            )
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            if saw_ws_failure:
                self._append_log(task.log_path, "history fallback was used")

    def _handle_ws_message(
        self,
        task: TaskRecord,
        prompt_id: str,
        message: Any,
        event_callback: TaskBackendCallback | None,
    ) -> TaskExecutionResult | None:
        if not isinstance(message, str):
            return None

        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            self._append_log(task.log_path, f"non-json websocket message: {message!r}")
            return None

        event_type = str(payload.get("type") or "")
        data = payload.get("data") or {}
        event_prompt_id = str(data.get("prompt_id") or "").strip()
        if event_prompt_id and event_prompt_id != prompt_id:
            return None

        if event_type == "status":
            self._emit_event(event_callback, task.log_path, "queued")
            return None

        if event_type == "progress":
            current = _coerce_optional_int(data.get("value"))
            total = _coerce_optional_int(data.get("max"))
            percent = None
            if current is not None and total:
                percent = min(100, int((current / total) * 100))
            self._emit_event(
                event_callback,
                task.log_path,
                "sampling",
                progress_current=current,
                progress_total=total,
                progress_percent=percent,
            )
            return None

        if event_type == "executing":
            node_id = str(data.get("node")) if data.get("node") is not None else None
            if node_id == str(SAVE_VIDEO_NODE_ID):
                self._emit_event(event_callback, task.log_path, "saving video")
            elif node_id is None and (not event_prompt_id or event_prompt_id == prompt_id):
                history = self._poll_history(task, prompt_id, event_callback)
                if history.terminal:
                    return self._history_outcome_to_result(history, prompt_id)
            else:
                self._emit_event(event_callback, task.log_path, "sampling")
            return None

        if event_type == "execution_error":
            error_message = _extract_error_message(data) or "ComfyUI execution failed"
            self._append_log(task.log_path, f"execution_error: {error_message}")
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message=error_message,
                failure_code=_failure_code_from_message(error_message),
                backend_prompt_id=prompt_id,
            )

        if event_type == "execution_success":
            history = self._poll_history(task, prompt_id, event_callback)
            if history.terminal:
                return self._history_outcome_to_result(history, prompt_id)
            self._emit_event(event_callback, task.log_path, "saving video")
            return None

        return None

    def _poll_history(
        self,
        task: TaskRecord,
        prompt_id: str,
        event_callback: TaskBackendCallback | None,
    ) -> HistoryOutcome:
        try:
            with httpx.Client(
                base_url=self.settings.comfyui_base_url,
                timeout=self.settings.comfyui_request_timeout_seconds,
            ) as client:
                response = client.get(f"/history/{prompt_id}")
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            self._append_log(task.log_path, f"history poll failed: {exc}")
            return HistoryOutcome(terminal=False)

        entry = _history_entry_for_prompt(payload, prompt_id)
        if entry is None:
            return HistoryOutcome(terminal=False)

        status_payload = entry.get("status") or {}
        status_text = str(
            status_payload.get("status_str")
            or status_payload.get("status")
            or entry.get("status_str")
            or ""
        ).lower()
        completed = bool(
            status_payload.get("completed")
            or status_text in {"success", "succeeded", "done", "error", "failed"}
        )

        if status_text in {"error", "failed"}:
            message = _extract_error_message(entry) or "ComfyUI execution failed"
            self._append_log(task.log_path, f"history failure: {message}")
            return HistoryOutcome(
                terminal=True,
                success=False,
                error_message=message,
                failure_code=_failure_code_from_message(message),
            )

        if completed:
            self._emit_event(event_callback, task.log_path, "saving video")
            return HistoryOutcome(terminal=True, success=True)

        self._emit_event(event_callback, task.log_path, "sampling")
        return HistoryOutcome(terminal=False)

    def _history_outcome_to_result(
        self,
        outcome: HistoryOutcome,
        prompt_id: str,
    ) -> TaskExecutionResult:
        if not outcome.terminal:
            return TaskExecutionResult(
                success=False,
                output_path=None,
                error_message="ComfyUI history did not reach a terminal state",
                failure_code="backend_execution_error",
                backend_prompt_id=prompt_id,
            )
        if outcome.success:
            return TaskExecutionResult(
                success=True,
                output_path="__pending_copy__",
                error_message=None,
                backend_prompt_id=prompt_id,
            )
        return TaskExecutionResult(
            success=False,
            output_path=None,
            error_message=outcome.error_message or "ComfyUI execution failed",
            failure_code=outcome.failure_code or "backend_execution_error",
            backend_prompt_id=prompt_id,
        )

    def _collect_output_file(self, output_prefix: str) -> Path | None:
        candidates = sorted(
            self.settings.comfyui_output_dir.rglob(f"{output_prefix}*.mp4"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

    def _emit_event(
        self,
        event_callback: TaskBackendCallback | None,
        log_path: str,
        status_message: str,
        *,
        backend_prompt_id: str | None = None,
        progress_current: int | None = None,
        progress_total: int | None = None,
        progress_percent: int | None = None,
    ) -> None:
        line = status_message
        if progress_current is not None and progress_total is not None:
            line = f"{status_message} {progress_current}/{progress_total}"
            if progress_percent is not None:
                line = f"{line} ({progress_percent}%)"
        self._append_log(log_path, line)
        if event_callback is None:
            return
        event_callback(
            TaskBackendEvent(
                progress=TaskProgressState(
                    status_message=status_message,
                    progress_current=progress_current,
                    progress_total=progress_total,
                    progress_percent=progress_percent,
                ),
                backend_prompt_id=backend_prompt_id,
            )
        )

    def _append_log(self, log_path: str, message: str) -> None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")


def _history_entry_for_prompt(payload: Any, prompt_id: str) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if prompt_id in payload and isinstance(payload[prompt_id], dict):
            return payload[prompt_id]
        if "prompt_id" in payload and str(payload.get("prompt_id")) == prompt_id:
            return payload
    return None


def _extract_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("exception_message", "error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        details = payload.get("details")
        if isinstance(details, str) and details.strip():
            return details.strip()
        status = payload.get("status")
        if isinstance(status, dict):
            nested = _extract_error_message(status)
            if nested:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_error_message(item)
            if nested:
                return nested
    return None


def _failure_code_from_message(message: str) -> str:
    lower = message.lower()
    if "out of memory" in lower or "cuda out of memory" in lower or "oom" in lower:
        return "backend_oom"
    if "validation" in lower or "node_errors" in lower:
        return "backend_validation_error"
    return "backend_execution_error"


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
