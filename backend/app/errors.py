from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


def _payload(code: str, message: str, details: object | None = None) -> dict[str, object]:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return {"error": body}


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    logger.warning("app error: {code} {message}", code=exc.code, message=exc.message)
    return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message))


def _safe_details(errors: list[dict[str, object]]) -> list[dict[str, object]]:
    # pydantic echoes the rejected value back, which would hand a mistyped
    # password or token straight to the caller
    return [
        {key: value for key, value in error.items() if key in ("loc", "msg", "type")}
        for error in errors
    ]


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content=_payload(
            "validation_error",
            "request payload is invalid",
            _safe_details(cast("list[dict[str, object]]", exc.errors())),
        ),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled error on {method} {path}", method=request.method, path=request.url.path
    )
    return JSONResponse(
        status_code=500,
        content=_payload("internal_error", "internal server error"),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
