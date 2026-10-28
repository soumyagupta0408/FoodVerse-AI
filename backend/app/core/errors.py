import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("foodverse.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details=None, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class ValidationFailed(AppError):
    status_code, code = 422, "validation_failed"


class PayloadTooLarge(AppError):
    status_code, code = 413, "payload_too_large"


class ModelUnavailable(AppError):
    """A required local model or provider is not installed/configured. Never faked."""

    status_code, code = 503, "model_unavailable"


class RateLimited(AppError):
    status_code, code = 429, "rate_limited"


def _body(request: Request, code: str, message: str, details=None):
    return {"error": {"code": code, "message": message, "details": details, "request_id": getattr(request.state, "request_id", None)}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_body(request, exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(status_code=422, content=_body(request, "validation_failed", "Request validation failed", details))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=_body(request, "http_error", str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content=_body(request, "internal_error", "Unexpected server error"))
