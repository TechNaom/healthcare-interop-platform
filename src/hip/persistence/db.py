"""Async database engine/session wiring.

Cloud-agnostic by design (ADR-003): the connection string comes from the
``HIP_DATABASE_URL`` environment variable, so the identical code runs against a
local Postgres container in dev and the client's own managed Postgres in
production — no code change, just config. Nothing here imports a cloud SDK.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSession

# Local dev default (synthetic data only). Overridden by env everywhere real.
_DEFAULT_URL = "postgresql+asyncpg://hip:hip@localhost:5432/hip"


def database_url() -> str:
    """Resolve the async SQLAlchemy database URL from the environment."""
    return os.environ.get("HIP_DATABASE_URL", _DEFAULT_URL)


def make_engine(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine. Pass ``url`` explicitly in tests."""
    return create_async_engine(url or database_url(), echo=echo, pool_pre_ping=True)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to an engine; business code holds sessions, not
    connections (docs/DESIGN.md — repositories sit behind persistence.*)."""
    return async_sessionmaker(engine, expire_on_commit=False)
