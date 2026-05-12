"""HTTP middleware: request-ID correlation + access logging."""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from biq.logging import set_request_id

_logger = logging.getLogger("biq.api.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a UUID (or echo the inbound X-Request-ID)
    and bind it to the contextvar consumed by `biq.logging`. Emits a
    structured access-log line per request."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get("X-Request-ID")
        rid = set_request_id(incoming)

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        response.headers["X-Request-ID"] = rid

        _logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
                "client": request.client.host if request.client else None,
            },
        )
        return response
