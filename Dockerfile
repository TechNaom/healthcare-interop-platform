# Multi-stage, multi-arch build (ADR-003). Base pinned to Python 3.12 (ADR-006).
# Build with buildx for linux/amd64 + linux/arm64:
#   docker buildx build --platform linux/amd64,linux/arm64 -t hip:local .
# Runtime deps come from the lockfile (uv sync --no-dev); the image also carries
# the Alembic migrations so it can create/upgrade its own schema on start.

# --- builder ---------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv for reproducible, lockfile-based installs (docs/TECH_STACK.md).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer — cached unless the lock/manifest changes.
# README.md is copied too: pyproject's `readme = "README.md"` means hatchling
# needs it present when it builds the project in the final `uv sync` below.
COPY pyproject.toml README.md ./
COPY uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev || uv sync --no-dev

# Project source.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# --- runtime ---------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Non-root by default — the container never needs root at runtime.
RUN useradd --system --create-home --uid 10001 appuser

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
# Migrations + Alembic config so the container can run `alembic upgrade head`.
COPY alembic.ini ./
COPY migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8000

# Serve the Gateway. Uvicorn binds all interfaces inside the container; the host
# and TLS termination are handled outside the process (Traefik — docs/TECH_STACK.md).
CMD ["uvicorn", "hip.gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]
