"""Observability init (env-gated).

Two integrations, both no-ops without their respective env keys:

- Sentry (SENTRY_DSN): unhandled exceptions + 10% transaction sample
  from FastAPI and SQLAlchemy.
- Langfuse (LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY): LLM observability
  — every investigator turn is wrapped in a generation span with usage,
  prompt, response, and the parent trace tied to the audit run_id.

Idempotent: calling twice is safe; the second call is a no-op once a
client is cached.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing langfuse at module load when unused
    from langfuse import Langfuse

_logger = logging.getLogger(__name__)
_langfuse: Langfuse | None = None
_langfuse_initialised = False


def init_sentry() -> None:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "local"),
        release=os.environ.get("APP_RELEASE", "dev"),
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        send_default_pii=False,
    )


def init_langfuse() -> Langfuse | None:
    """Return a cached Langfuse client if env keys are set; otherwise None.

    Safe to call from any entry point — investigator init, CLI, tests.
    Failures inside the SDK never propagate: if Langfuse can't be reached
    we log a warning and return None so the investigator keeps running.
    """
    global _langfuse, _langfuse_initialised
    if _langfuse_initialised:
        return _langfuse

    _langfuse_initialised = True

    public = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret = os.environ.get("LANGFUSE_SECRET_KEY")
    if not public or not secret:
        return None

    try:
        from langfuse import Langfuse

        _langfuse = Langfuse(
            public_key=public,
            secret_key=secret,
            host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            environment=os.environ.get("APP_ENV", "local"),
        )
    except Exception as exc:  # pragma: no cover — depends on network state
        _logger.warning("Langfuse init failed: %s. Tracing disabled.", exc)
        _langfuse = None

    return _langfuse
