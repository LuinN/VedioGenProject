from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

ERROR_STATUS_CODES = {
    "unsupported_mode": status.HTTP_400_BAD_REQUEST,
    "invalid_size": status.HTTP_400_BAD_REQUEST,
    "validation_error": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "task_not_found": status.HTTP_404_NOT_FOUND,
    "result_not_ready": status.HTTP_409_CONFLICT,
    "result_file_missing": status.HTTP_404_NOT_FOUND,
    "service_not_ready": status.HTTP_503_SERVICE_UNAVAILABLE,
    "wan_execution_failed": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


@dataclass(slots=True)
class ApiError(Exception):
    code: str
    message: str

    @property
    def status_code(self) -> int:
        return ERROR_STATUS_CODES[self.code]


def error_payload(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(exc.code, exc.message),
    )


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else None
    if first_error:
        location = ".".join(str(item) for item in first_error.get("loc", []))
        message = first_error.get("msg", "Request validation failed")
        if location:
            message = f"{location}: {message}"
    else:
        message = "Request validation failed"
    return JSONResponse(
        status_code=ERROR_STATUS_CODES["validation_error"],
        content=error_payload("validation_error", message),
    )


async def unhandled_error_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=ERROR_STATUS_CODES["wan_execution_failed"],
        content=error_payload(
            "wan_execution_failed",
            "The service encountered an unexpected internal error.",
        ),
    )
