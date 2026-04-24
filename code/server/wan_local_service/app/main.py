from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from .config import (
    API_MODE_T2V,
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    SERVICE_NAME,
    Settings,
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
)
from .task_runtime import (
    build_task_runtime_snapshot,
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


def _task_to_response(task: TaskRecord) -> TaskCreateResponse:
    return TaskCreateResponse(
        task_id=task.task_id,
        status=task.status,
        prompt=task.prompt,
        output_path=task.output_path,
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
    runtime_snapshot = build_task_runtime_snapshot(
        task.log_path,
        output_path=task.output_path,
        expected_output=expected_output_path(settings.outputs_dir, task.task_id),
    )
    return TaskDetailResponse(
        **_task_to_response(task).model_dump(),
        output_exists=runtime_snapshot.output_exists,
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
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_task(request: Request, payload: TaskCreateRequest) -> TaskCreateResponse:
    context = _get_context(request)
    if payload.mode != API_MODE_T2V:
        raise ApiError(
            "unsupported_mode",
            f"Unsupported mode '{payload.mode}'. Only 't2v' is supported.",
        )
    if payload.size not in context.settings.allowed_sizes:
        raise ApiError(
            "invalid_size",
            (
                f"Invalid size '{payload.size}'. Supported sizes: "
                f"{', '.join(context.settings.allowed_sizes)}."
            ),
        )

    task_id = str(uuid4())
    log_path = str((context.settings.logs_dir / f"{task_id}.log").resolve())
    task = context.repository.create_task(
        task_id=task_id,
        mode=payload.mode,
        prompt=payload.prompt,
        size=payload.size,
        log_path=log_path,
    )
    try:
        await context.runner.enqueue(task.task_id)
    except RuntimeError as exc:
        raise ApiError("service_not_ready", str(exc)) from exc
    return _task_to_response(task)


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
