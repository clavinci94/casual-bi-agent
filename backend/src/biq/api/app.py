"""FastAPI app wiring.

Mounts the resource routers under /api/* and exposes /healthz, /readyz at
the root. OpenAPI docs are auto-generated at /docs and /redoc.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from biq import __version__
from biq.api import health, investigations, kg, kpi, recommendations, runs
from biq.api.auth import require_api_key
from biq.api.middleware import RequestIDMiddleware
from biq.api.rate_limit import limiter
from biq.logging import configure_logging
from biq.observability import init_sentry

# Side effects up-front so anything imported later also sees them
configure_logging()
init_sentry()

app = FastAPI(
    title="Causal BI",
    version=__version__,
    description=(
        "Agentic Business Intelligence with causal inference and human-in-the-loop. "
        "See /docs for OpenAPI schema."
    ),
)

# Wide-open CORS for the demo. Lock down to the Streamlit/Next.js origin in prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.state.limiter = limiter


def _rate_limit_handler(request, exc: RateLimitExceeded):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={"detail": "rate limit exceeded", "retry_after": exc.detail},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

# Health endpoints at root (Render / k8s style) — never gated
app.include_router(health.router)

# Domain routes under /api — gated by X-API-Key when BIQ_API_KEY is set
_protected = [Depends(require_api_key)]
app.include_router(recommendations.router, prefix="/api", dependencies=_protected)
app.include_router(runs.router, prefix="/api", dependencies=_protected)
app.include_router(kpi.router, prefix="/api", dependencies=_protected)
app.include_router(investigations.router, prefix="/api", dependencies=_protected)
app.include_router(kg.router, prefix="/api", dependencies=_protected)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "name": "Causal BI",
        "version": __version__,
        "docs": "/docs",
        "health": "/healthz",
    }
