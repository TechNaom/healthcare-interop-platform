"""FastAPI dependencies for the gateway.

The DB session factory is created once at app startup (see ``app.lifespan``) and
stored on ``app.state``; ``get_session`` hands each request its own session and
guarantees cleanup. Keeping the engine on app state (not a module global) makes
tests able to build isolated apps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session from the app's session factory."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session
