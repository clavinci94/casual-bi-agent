"""Structured logging with request-ID correlation.

JSON-formatted logs to stdout (the 12-factor + Render/Kubernetes way).
A request_id ContextVar propagates through async handlers so every log
line emitted during a request carries the same id — set once by the
FastAPI middleware, available everywhere via `get_request_id()`.

Wire-up: call `configure_logging()` once at startup (already done in
biq.api.app). Use `logging.getLogger(__name__)` everywhere else.
"""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

from biq.config import settings

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


def configure_logging() -> None:
    """Idempotent — safe to call from app startup AND from tests."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s %(request_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    # Clear preexisting handlers so reloading doesn't double-log
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # Tame uvicorn's access-log noise; we emit our own request line via
    # the middleware so duplicate logs don't help operators.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def set_request_id(rid: str | None = None) -> str:
    rid = rid or str(uuid.uuid4())
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    return _request_id.get()
