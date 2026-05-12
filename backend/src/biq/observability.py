"""Sentry init (env-gated).

If `SENTRY_DSN` is set, captures unhandled exceptions and a 10% trace
sample from FastAPI + SQLAlchemy. No-op when unset, so dev and CI never
phone home.
"""

from __future__ import annotations

import os


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
