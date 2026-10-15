import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from app.core.json import OrjsonResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_request: Request, exc: AppError) -> OrjsonResponse:
        return OrjsonResponse(
            error_body(exc.code, exc.message), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        _request: Request, _exc: RequestValidationError
    ) -> OrjsonResponse:
        return OrjsonResponse(
            error_body("validation_error", "Invalid request"), status_code=422
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> OrjsonResponse:
        detail: Any = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            return OrjsonResponse(
                error_body(
                    str(detail["code"]), str(detail.get("message", "Request failed"))
                ),
                status_code=exc.status_code,
            )
        return OrjsonResponse(
            error_body(
                "unauthorized" if exc.status_code == 401 else "internal_error",
                str(detail),
            ),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> OrjsonResponse:
        logger.exception("Request failed: %s", request.url.path, exc_info=exc)
        return OrjsonResponse(
            error_body("internal_error", "Internal server error"), status_code=500
        )
