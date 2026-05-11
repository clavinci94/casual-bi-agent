# Backend container (FastAPI + agents + MCP server).
# uv-based image so the lockfile is the source of truth.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install deps first for better layer caching
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source
COPY backend/src ./src
COPY backend/scripts ./scripts
COPY db ./db
COPY docs ./docs

# Final sync to install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
ENV APP_ENV=production
EXPOSE 8000

# Default to the API entrypoint (TBD — FastAPI app at src/biq/api/app.py).
# Until that exists, the container is used as a tool runner via docker exec.
CMD ["uv", "run", "uvicorn", "biq.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
