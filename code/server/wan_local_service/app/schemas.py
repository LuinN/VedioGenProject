from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    ok: bool
    service: str


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = Field(..., description="Supported modes: t2v or i2v.")
    prompt: str = Field(..., description="The text prompt used to generate the video.")
    size: str = Field(..., description="The output resolution token.")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("prompt must not be empty")
        return cleaned


class TaskResponseBase(BaseModel):
    task_id: str
    mode: str
    status: str
    prompt: str
    size: str
    output_path: Optional[str] = None
    input_image_path: Optional[str] = None
    error_message: Optional[str] = None
    log_path: str
    create_time: str
    update_time: str


class TaskCreateResponse(TaskResponseBase):
    pass


class TaskDetailResponse(TaskResponseBase):
    output_exists: bool
    input_image_exists: bool
    status_message: Optional[str] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_percent: Optional[int] = None
    download_url: Optional[str] = None


class TaskProgressResponse(BaseModel):
    task_id: str
    status: str
    update_time: str
    output_exists: bool
    error_message: Optional[str] = None
    status_message: Optional[str] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None
    progress_percent: Optional[int] = None
    download_url: Optional[str] = None


class TaskDeleteResponse(BaseModel):
    task_id: str
    deleted: bool


class TaskListItemResponse(TaskResponseBase):
    pass


class TaskListResponse(BaseModel):
    items: list[TaskListItemResponse]
    total: int
    limit: int


class ResultItemResponse(BaseModel):
    task_id: str
    output_path: str
    create_time: str
    output_exists: bool
    download_url: Optional[str] = None


class ResultListResponse(BaseModel):
    items: list[ResultItemResponse]
    total: int
    limit: int
