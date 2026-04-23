from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from fastapi import FastAPI, Query, Request, status
from fastapi.exceptions import RequestValidationError

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


def _task_to_detail(task: TaskRecord) -> TaskDetailResponse:
    return TaskDetailResponse(
        **_task_to_response(task).model_dump(),
        output_exists=_output_exists(task.output_path),
    )


def _task_to_list_item(task: TaskRecord) -> TaskListItemResponse:
    return TaskListItemResponse(**_task_to_response(task).model_dump())


def _task_to_result_item(task: TaskRecord) -> ResultItemResponse:
    if task.output_path is None:
        raise ValueError(f"task {task.task_id} is missing output_path")
    return ResultItemResponse(
        task_id=task.task_id,
        output_path=task.output_path,
        create_time=task.create_time,
        output_exists=_output_exists(task.output_path),
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> Iterator[None]:
    settings = load_settings()
    settings.ensure_directories()
    init_db(settings.db_path)
    repository = TaskRepository(settings.db_path)
    repository.recover_interrupted_tasks()
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
    return _task_to_detail(task)


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
    tasks = context.repository.list_tasks(limit)
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
    results = context.repository.list_results(limit)
    return ResultListResponse(
        items=[_task_to_result_item(task) for task in results],
        total=context.repository.count_results(),
        limit=limit,
    )
