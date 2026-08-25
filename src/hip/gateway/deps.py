"""FastAPI dependencies for the gateway.

The DB session factory is created once at app startup (see ``app.lifespan``) and
stored on ``app.state``; ``get_session`` hands each request its own session and
guarantees cleanup. Keeping the engine on app state (not a module global) makes
tests able to build isolated apps.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from hip.gateway.auth import AuthError, Principal, TokenAuthenticator


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session from the app's session factory."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


async def get_principal(request: Request) -> Principal:
    """Authenticate the bearer token into a Principal (raises AuthError)."""
    authenticator: TokenAuthenticator = request.app.state.authenticator
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError(401, "login", "missing bearer token")
    return authenticator.authenticate(token)


def require_role(role: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Dependency factory: require the caller to hold ``role`` (RBAC)."""

    async def _dep(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if not principal.has_role(role):
            raise AuthError(403, "forbidden", f"requires role '{role}'")
        return principal

    return _dep
