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
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped async session from the app's session factory."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_key_manager(request: Request) -> KeyManager:
    """The configured KeyManager, or fail closed if encryption isn't configured."""
    key_manager: KeyManager | None = request.app.state.key_manager
    if key_manager is None:
        raise AuthError(500, "exception", "encryption is not configured")
    return key_manager


def get_optional_blind_indexer(request: Request) -> BlindIndexer | None:
    """The blind indexer if configured, else None (writes just skip indexing)."""
    indexer: BlindIndexer | None = getattr(request.app.state, "blind_indexer", None)
    return indexer


def get_blind_indexer(request: Request) -> BlindIndexer:
    """The blind indexer, or fail closed (search unavailable) if not configured."""
    indexer = get_optional_blind_indexer(request)
    if indexer is None:
        raise AuthError(503, "not-supported", "search is not configured")
    return indexer


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
