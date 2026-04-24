from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.datastructures import UploadFile as StarletteUploadFile

from .config import (
    API_MODES,
    API_MODE_I2V,
    API_MODE_T2V,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    SERVICE_NAME,
    Settings,
    SUPPORTED_INPUT_IMAGE_CONTENT_TYPES,
    SUPPORTED_INPUT_IMAGE_EXTENSIONS,
    load_settings,
)
from .db import init_db
from .errors import (
    ApiError,
    api_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from .repository import TaskRecord, TaskRepository
from .schemas import (
    ErrorResponse,
    HealthResponse,
    ResultItemResponse,
    ResultListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskDetailResponse,
    TaskListItemResponse,
    TaskListResponse,
    TaskProgressResponse,
)
from .task_runtime import (
    build_task_progress_snapshot,
    expected_output_path,
    reconcile_task_completion,
    recover_interrupted_tasks,
)
from .task_runner import TaskRunner
from .wan_runner import WanRunner


@dataclass(slots=True)
class ServiceContext:
    settings: Settings
    repository: TaskRepository
    runner: TaskRunner
    ready: bool = False


@dataclass(slots=True)
class ParsedTaskCreateRequest:
    payload: TaskCreateRequest
    image: StarletteUploadFile | None = None


def _task_to_response(task: TaskRecord) -> TaskCreateResponse:
    return TaskCreateResponse(
        task_id=task.task_id,
        mode=task.mode,
        status=task.status,
        prompt=task.prompt,
        size=task.size,
        output_path=task.output_path,
        input_image_path=task.input_image_path,
        error_message=task.error_message,
        log_path=task.log_path,
        create_time=task.create_time,
        update_time=task.update_time,
    )


def _build_download_url(request: Request, task: TaskRecord, *, output_exists: bool) -> str | None:
    if task.status != "succeeded" or not output_exists:
        return None
    return str(request.url_for("download_result_file", task_id=task.task_id))


def _task_to_detail(
    request: Request,
    task: TaskRecord,
    settings: Settings,
) -> TaskDetailResponse:
    runtime_snapshot = build_task_progress_snapshot(
        task,
        expected_output=expected_output_path(settings.outputs_dir, task.task_id),
    )
    return TaskDetailResponse(
        **_task_to_response(task).model_dump(),
        output_exists=runtime_snapshot.output_exists,
        input_image_exists=_input_exists(task.input_image_path),
        status_message=runtime_snapshot.status_message,
        progress_current=runtime_snapshot.progress_current,
        progress_total=runtime_snapshot.progress_total,
        progress_percent=runtime_snapshot.progress_percent,
        download_url=_build_download_url(
            request,
            task,
            output_exists=runtime_snapshot.output_exists,
        ),
    )


def _task_to_progress(
    request: Request,
    task: TaskRecord,
    settings: Settings,
) -> TaskProgressResponse:
    runtime_snapshot = build_task_progress_snapshot(
        task,
        expected_output=expected_output_path(settings.outputs_dir, task.task_id),
    )
    return TaskProgressResponse(
        task_id=task.task_id,
        status=task.status,
        update_time=task.update_time,
        output_exists=runtime_snapshot.output_exists,
        error_message=task.error_message,
        status_message=runtime_snapshot.status_message,
        progress_current=runtime_snapshot.progress_current,
        progress_total=runtime_snapshot.progress_total,
        progress_percent=runtime_snapshot.progress_percent,
        download_url=_build_download_url(
            request,
            task,
            output_exists=runtime_snapshot.output_exists,
        ),
    )


def _task_to_list_item(task: TaskRecord) -> TaskListItemResponse:
    return TaskListItemResponse(**_task_to_response(task).model_dump())


def _task_to_result_item(request: Request, task: TaskRecord) -> ResultItemResponse:
    if task.output_path is None:
        raise ValueError(f"task {task.task_id} is missing output_path")
    output_exists = _output_exists(task.output_path)
    return ResultItemResponse(
        task_id=task.task_id,
        output_path=task.output_path,
        create_time=task.create_time,
        output_exists=output_exists,
        download_url=_build_download_url(request, task, output_exists=output_exists),
    )


def _output_exists(output_path: str | None) -> bool:
    return bool(output_path) and Path(output_path).exists()


def _input_exists(input_image_path: str | None) -> bool:
    return bool(input_image_path) and Path(input_image_path).exists()


def _validation_message_from_errors(errors: list[dict[str, Any]]) -> str:
    first_error = errors[0] if errors else None
    if first_error:
        location = ".".join(str(item) for item in first_error.get("loc", []))
        message = first_error.get("msg", "Request validation failed")
        if location:
            return f"{location}: {message}"
        return str(message)
    return "Request validation failed"


def _validate_task_create_payload(
    context: ServiceContext,
    payload: TaskCreateRequest,
    image: StarletteUploadFile | None,
) -> None:
    if payload.mode not in API_MODES:
        raise ApiError(
            "unsupported_mode",
            (
                f"Unsupported mode '{payload.mode}'. Supported modes: "
                f"{', '.join(API_MODES)}."
            ),
        )
    if payload.size not in context.settings.allowed_sizes:
        raise ApiError(
            "invalid_size",
            (
                f"Invalid size '{payload.size}'. Supported sizes: "
                f"{', '.join(context.settings.allowed_sizes)}."
            ),
        )
    if payload.mode == API_MODE_I2V and image is None:
        raise ApiError(
            "image_required",
            "mode 'i2v' requires an uploaded image in multipart/form-data.",
        )
    if payload.mode == API_MODE_T2V and image is not None:
        raise ApiError(
            "validation_error",
            "body.image: image uploads are only supported when mode is 'i2v'.",
        )


def _read_string_field(raw_value: Any, field_name: str) -> str:
    if raw_value is None:
        raise ApiError("validation_error", f"body.{field_name}: Field required")
    if not isinstance(raw_value, str):
        raise ApiError(
            "validation_error",
            f"body.{field_name}: Input should be a valid string",
        )
    return raw_value


async def _parse_json_task_create_request(request: Request) -> ParsedTaskCreateRequest:
    try:
        raw_payload = await request.json()
    except ValueError as exc:
        raise ApiError("validation_error", "body: Request body is not valid JSON.") from exc

    try:
        payload = TaskCreateRequest.model_validate(raw_payload)
    except ValidationError as exc:
        raise ApiError(
            "validation_error",
            _validation_message_from_errors(exc.errors()),
        ) from exc
    return ParsedTaskCreateRequest(payload=payload)


async def _parse_form_task_create_request(request: Request) -> ParsedTaskCreateRequest:
    try:
        form = await request.form()
    except Exception as exc:
        raise ApiError(
            "validation_error",
            "body: Request body is not valid multipart/form-data.",
        ) from exc

    image_value = form.get("image")
    if image_value is not None and not isinstance(image_value, StarletteUploadFile):
        raise ApiError(
            "validation_error",
            "body.image: Input should be a file upload.",
        )

    image = (
        image_value
        if isinstance(image_value, StarletteUploadFile)
        and bool((image_value.filename or "").strip())
        else None
    )

    try:
        payload = TaskCreateRequest.model_validate(
            {
                "mode": _read_string_field(form.get("mode"), "mode"),
                "prompt": _read_string_field(form.get("prompt"), "prompt"),
                "size": _read_string_field(form.get("size"), "size"),
            }
        )
    except ValidationError as exc:
        raise ApiError(
            "validation_error",
            _validation_message_from_errors(exc.errors()),
        ) from exc
    return ParsedTaskCreateRequest(payload=payload, image=image)


async def _parse_task_create_request(request: Request) -> ParsedTaskCreateRequest:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        return await _parse_json_task_create_request(request)
    if content_type.startswith("multipart/form-data"):
        return await _parse_form_task_create_request(request)
    raise ApiError(
        "validation_error",
        "body: Content-Type must be application/json or multipart/form-data.",
    )


def _task_output_dir(settings: Settings, task_id: str) -> Path:
    return settings.outputs_dir / task_id


async def _save_input_image(
    settings: Settings,
    task_id: str,
    image: StarletteUploadFile,
) -> str:
    suffix = Path(image.filename or "").suffix.lower()
    if suffix not in SUPPORTED_INPUT_IMAGE_EXTENSIONS:
        raise ApiError(
            "image_not_supported",
            (
                f"Unsupported image extension '{suffix or '<missing>'}'. Supported "
                f"formats: {', '.join(ext.lstrip('.') for ext in SUPPORTED_INPUT_IMAGE_EXTENSIONS)}."
            ),
        )

    content_type = (image.content_type or "").strip().lower()
    allowed_content_types = SUPPORTED_INPUT_IMAGE_CONTENT_TYPES[suffix]
    if content_type and content_type not in allowed_content_types:
        raise ApiError(
            "image_not_supported",
            (
                f"Unsupported image content type '{content_type}'. Expected one of: "
                f"{', '.join(allowed_content_types)}."
            ),
        )

    output_dir = _task_output_dir(settings, task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = (output_dir / f"input_image{suffix}").resolve()

    bytes_written = 0
    try:
        with image_path.open("wb") as output_file:
            while True:
                chunk = await image.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > settings.max_input_image_bytes:
                    raise ApiError(
                        "image_too_large",
                        (
                            "Uploaded image is too large. Maximum size is "
                            f"{settings.max_input_image_bytes} bytes."
                        ),
                    )
                output_file.write(chunk)
    except ApiError:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except OSError as exc:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ApiError(
            "image_save_failed",
            f"Failed to save uploaded image: {exc}",
        ) from exc

    if bytes_written == 0:
        try:
            image_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise ApiError(
            "validation_error",
            "body.image: Uploaded image must not be empty.",
        )

    return str(image_path)


def _get_context(request: Request) -> ServiceContext:
    context = getattr(request.app.state, "service_context", None)
    if not isinstance(context, ServiceContext):
        raise ApiError("service_not_ready", "The service context is not available.")
    if not context.ready:
        raise ApiError("service_not_ready", "The service is not ready to accept tasks.")
    return context


def _reconcile_task(context: ServiceContext, task: TaskRecord) -> TaskRecord:
    return reconcile_task_completion(
        context.repository,
        context.settings.outputs_dir,
        task,
    )


def _reconcile_incomplete_tasks(context: ServiceContext) -> None:
    tasks = context.repository.list_tasks_by_statuses(("pending", "running"))
    for task in tasks:
        _reconcile_task(context, task)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Iterator[None]:
    settings = load_settings()
    settings.ensure_directories()
    init_db(settings.db_path)
    repository = TaskRepository(settings.db_path)
    recover_interrupted_tasks(repository, settings.outputs_dir)
    runner = TaskRunner(repository, WanRunner(settings))
    await runner.start()
    context = ServiceContext(
        settings=settings,
        repository=repository,
        runner=runner,
        ready=True,
    )
    app.state.service_context = context
    try:
        yield
    finally:
        context.ready = False
        await runner.stop()


app = FastAPI(
    title="Wan Local Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_error_handler)


@app.get(
    "/healthz",
    response_model=HealthResponse,
    responses={500: {"model": ErrorResponse}},
)
async def healthz() -> HealthResponse:
    return HealthResponse(ok=True, service=SERVICE_NAME)


@app.post(
    "/api/tasks",
    response_model=TaskCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_task(request: Request) -> TaskCreateResponse:
    context = _get_context(request)
    parsed = await _parse_task_create_request(request)
    _validate_task_create_payload(context, parsed.payload, parsed.image)
    task_id = str(uuid4())
    log_path = str((context.settings.logs_dir / f"{task_id}.log").resolve())
    try:
        input_image_path = None
        if parsed.image is not None:
            input_image_path = await _save_input_image(
                context.settings,
                task_id,
                parsed.image,
            )
        task = context.repository.create_task(
            task_id=task_id,
            mode=parsed.payload.mode,
            prompt=parsed.payload.prompt,
            size=parsed.payload.size,
            log_path=log_path,
            input_image_path=input_image_path,
        )
        try:
            await context.runner.enqueue(task.task_id)
        except RuntimeError as exc:
            raise ApiError("service_not_ready", str(exc)) from exc
        return _task_to_response(task)
    finally:
        if parsed.image is not None:
            await parsed.image.close()


@app.get(
    "/api/tasks/{task_id}",
    response_model=TaskDetailResponse,
    responses={
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_task(request: Request, task_id: str) -> TaskDetailResponse:
    context = _get_context(request)
    task = context.repository.get_task(task_id)
    if task is None:
        raise ApiError("task_not_found", f"Task '{task_id}' was not found.")
    task = _reconcile_task(context, task)
    return _task_to_detail(request, task, context.settings)


@app.get(
    "/api/tasks/{task_id}/progress",
    response_model=TaskProgressResponse,
    responses={
        404: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_task_progress(request: Request, task_id: str) -> TaskProgressResponse:
    context = _get_context(request)
    task = context.repository.get_task(task_id)
    if task is None:
        raise ApiError("task_not_found", f"Task '{task_id}' was not found.")
    task = _reconcile_task(context, task)
    return _task_to_progress(request, task, context.settings)


@app.get(
    "/api/tasks",
    response_model=TaskListResponse,
    responses={
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_tasks(
    request: Request,
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
) -> TaskListResponse:
    context = _get_context(request)
    tasks = [_reconcile_task(context, task) for task in context.repository.list_tasks(limit)]
    return TaskListResponse(
        items=[_task_to_list_item(task) for task in tasks],
        total=context.repository.count_tasks(),
        limit=limit,
    )


@app.get(
    "/api/results",
    response_model=ResultListResponse,
    responses={
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_results(
    request: Request,
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
) -> ResultListResponse:
    context = _get_context(request)
    _reconcile_incomplete_tasks(context)
    results = context.repository.list_results(limit)
    return ResultListResponse(
        items=[_task_to_result_item(request, task) for task in results],
        total=context.repository.count_results(),
        limit=limit,
    )


@app.get(
    "/api/results/{task_id}/file",
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def download_result_file(request: Request, task_id: str) -> Response:
    context = _get_context(request)
    task = context.repository.get_task(task_id)
    if task is None:
        raise ApiError("task_not_found", f"Task '{task_id}' was not found.")
    task = _reconcile_task(context, task)
    if task.status != "succeeded" or task.output_path is None:
        raise ApiError(
            "result_not_ready",
            f"Task '{task_id}' does not have a downloadable result yet.",
        )
    output_path = expected_output_path(context.settings.outputs_dir, task.task_id)
    if not output_path.exists():
        raise ApiError(
            "result_file_missing",
            f"Result file for task '{task_id}' was not found on the server.",
        )
    headers = {
        "Content-Disposition": f'attachment; filename="{task.task_id}.mp4"',
        "Content-Length": str(output_path.stat().st_size),
    }
    return Response(
        content=output_path.read_bytes(),
        media_type="video/mp4",
        headers=headers,
    )
