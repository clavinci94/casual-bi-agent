# Production backend image.
# - uv-managed deps with uv.lock as source of truth
# - Non-root user (UID 1000)
# - tini for proper signal handling so SIGTERM gracefully shuts down uvicorn
# - alembic upgrade head on entry — schema migrations are part of deploy
# - HEALTHCHECK for orchestrators (Render uses /healthz directly too)

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base

# tini for signal forwarding, curl for HEALTHCHECK, libpq5 for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user owns /app
RUN groupadd --gid 1000 biq && \
    useradd --uid 1000 --gid biq --shell /bin/bash --create-home biq

WORKDIR /app

# Install deps first for layer cache
COPY --chown=biq:biq backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Project sources
COPY --chown=biq:biq backend/src ./src
COPY --chown=biq:biq backend/scripts ./scripts
COPY --chown=biq:biq backend/alembic.ini ./
COPY --chown=biq:biq backend/alembic ./alembic
COPY --chown=biq:biq db ./db
COPY --chown=biq:biq docs ./docs

# Final sync installs the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Drop privileges
USER biq
ENV PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
# Run migrations then start the API. PORT comes from Render.
CMD ["sh", "-c", "alembic upgrade head && uvicorn biq.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
