"""Domain-agnostic exception types and FastAPI exception handlers.

Domain modules raise these instead of constructing HTTPException directly,
keeping business logic free of HTTP-layer concerns.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class NiveshError(Exception):
    """Base class for all application-raised errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class NotFoundError(NiveshError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ValidationFailedError(NiveshError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_FAILED"


class NotImplementedYetError(NiveshError):
    """Raised by placeholder service/repository methods in this scaffold."""

    status_code = status.HTTP_501_NOT_IMPLEMENTED
    error_code = "NOT_IMPLEMENTED"


def _error_envelope(code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NiveshError)
    async def handle_nivesh_error(request: Request, exc: NiveshError) -> JSONResponse:
        logger.warning("handled_error", extra={"code": exc.error_code, "path": request.url.path})
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_envelope(exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_envelope("INTERNAL_ERROR", "An unexpected error occurred.", {}),
        )
