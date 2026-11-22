"""Conversion of internal exceptions into a stable public JSON contract."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from agentic_commerce_platform.api.middleware import get_request_id
from agentic_commerce_platform.domain.errors import (
    AgentExecutionError,
    ConfigurationError,
    EcommercePlatformError,
    ExternalServiceError,
)
from agentic_commerce_platform.domain.models import ErrorDetail, ErrorResponse

__all__ = ["register_exception_handlers"]

logger = logging.getLogger(__name__)

_PLATFORM_ERROR_SPECS: tuple[tuple[type[EcommercePlatformError], int, str, str], ...] = (
    (
        ConfigurationError,
        500,
        "configuration_error",
        "服务配置异常，请稍后重试。",
    ),
    (
        AgentExecutionError,
        502,
        "agent_execution_error",
        "推荐 Agent 执行失败，请稍后重试。",
    ),
    (
        ExternalServiceError,
        503,
        "external_service_error",
        "外部服务暂时不可用，请稍后重试。",
    ),
    (
        EcommercePlatformError,
        500,
        "platform_error",
        "服务处理请求时发生错误。",
    ),
)

_HTTP_ERROR_MESSAGES: dict[int, tuple[str, str]] = {
    400: ("bad_request", "请求无效。"),
    401: ("unauthorized", "请求未授权。"),
    403: ("forbidden", "无权访问该资源。"),
    404: ("not_found", "请求的资源不存在。"),
    405: ("method_not_allowed", "请求方法不被允许。"),
}


def _json_error(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    """Build a JSON error response that always includes the request ID."""
    request_id = get_request_id(request)
    payload = ErrorResponse(
        request_id=request_id,
        error=ErrorDetail(code=code, message=message, details=details),
    ).model_dump(mode="json")
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Request-ID": request_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register API-wide handlers for validation, domain, and unknown errors."""

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        """Return field locations without echoing potentially sensitive input."""
        errors = [
            {
                "loc": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "invalid value"),
                "type": error.get("type", "value_error"),
            }
            for error in exc.errors()
        ]
        logger.warning(
            "request_validation_failed",
            extra={
                "http_path": request.url.path,
                "error_code": "validation_error",
            },
        )
        return _json_error(
            request,
            status_code=422,
            code="validation_error",
            message="请求参数校验失败。",
            details={"errors": errors},
        )

    @app.exception_handler(EcommercePlatformError)
    async def handle_platform_error(
        request: Request,
        exc: EcommercePlatformError,
    ) -> JSONResponse:
        """Log the internal failure but return only a stable public message."""
        status_code, public_code, public_message = _platform_error_spec(exc)
        logger.error(
            "handled_platform_error: %s",
            exc.message,
            extra={
                "http_path": request.url.path,
                "error_code": exc.code,
            },
        )
        return _json_error(
            request,
            status_code=status_code,
            code=public_code,
            message=public_message,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        """Convert framework HTTP errors into the same stable envelope."""
        public_code, public_message = _HTTP_ERROR_MESSAGES.get(
            exc.status_code,
            ("http_error", "请求处理失败。"),
        )
        logger.warning(
            "http_exception",
            extra={
                "http_path": request.url.path,
                "status_code": exc.status_code,
                "error_code": public_code,
            },
        )
        return _json_error(
            request,
            status_code=exc.status_code,
            code=public_code,
            message=public_message,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        """Log unknown failures with a traceback and return a generic 500."""
        logger.exception(
            "unhandled_exception",
            extra={"http_path": request.url.path, "error_code": "internal_error"},
        )
        return _json_error(
            request,
            status_code=500,
            code="internal_error",
            message="服务内部错误，请稍后重试。",
        )


def _platform_error_spec(exc: EcommercePlatformError) -> tuple[int, str, str]:
    """Map a project exception to an HTTP status and public error payload."""
    for error_type, status_code, code, message in _PLATFORM_ERROR_SPECS:
        if isinstance(exc, error_type):
            return status_code, code, message
    return 500, "platform_error", "服务处理请求时发生错误。"
