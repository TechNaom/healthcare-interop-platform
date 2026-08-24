# Multi-stage, multi-arch build (ADR-003). Base pinned to Python 3.12 (ADR-006).
# Build with buildx for linux/amd64 + linux/arm64:
#   docker buildx build --platform linux/amd64,linux/arm64 -t hip:local .
#
# NOTE (Phase 0): the app has no runtime deps yet, so `uv sync` installs only the
# project itself. Real service dependencies land in the phase that builds them.

# --- builder ---------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv for reproducible, lockfile-based installs (docs/TECH_STACK.md).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer — cached unless the lock/manifest changes.
COPY pyproject.toml ./
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

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

# Placeholder entrypoint until the gateway app exists (Phase 1). Kept as a
# module invocation so it fails loudly if the package can't be imported.
CMD ["python", "-c", "import hip; print(hip.__doc__)"]
