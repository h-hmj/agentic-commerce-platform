"""HTTP request correlation and access logging."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response

from agentic_commerce_platform.infrastructure.observability.logging import request_log_context

__all__ = ["get_request_id", "install_request_middleware", "resolve_request_id"]

logger = logging.getLogger(__name__)

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


def resolve_request_id(candidate: str | None) -> str:
    """Accept a safe caller-supplied correlation ID or generate a UUID.

    Args:
        candidate: Optional value from the ``X-Request-ID`` request header.

    Returns:
        A header-safe request identifier of at most 64 characters.
    """
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


def get_request_id(request: Request) -> str:
    """Return the request correlation ID, creating one only as a fallback.

    Middleware normally populates this before route handling. The fallback keeps
    exception handlers robust when invoked outside the normal middleware stack.
    """
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    return request_id


def install_request_middleware(app: FastAPI) -> None:
    """Install request correlation, structured access logs, and timing headers."""

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        started_at = time.perf_counter()
        log_extra = {
            "http_method": request.method,
            "http_path": request.url.path,
        }

        with request_log_context(request_id):
            logger.info("http_request_started", extra=log_extra)
            try:
                response = await call_next(request)
            except Exception:
                logger.exception(
                    "http_request_failed",
                    extra={
                        **log_extra,
                        "duration_ms": round(
                            (time.perf_counter() - started_at) * 1000.0, 2
                        ),
                    },
                )
                raise

            duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
            response.headers["X-Request-ID"] = request_id
            completion_extra = {
                **log_extra,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }
            if response.status_code >= 400:
                logger.warning("http_request_failed", extra=completion_extra)
            else:
                logger.info("http_request_succeeded", extra=completion_extra)
            return response
