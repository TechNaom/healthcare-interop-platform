"""FastAPI application factory for the Integration Gateway.

Assembles the outward API surface (docs/DESIGN.md 1): admin/health now, FHIR
routes as they land (Phase 6-7). A factory (``create_app``) rather than a
module-level singleton keeps tests able to build isolated app instances, while
``app`` at module scope is the ASGI target for uvicorn / the container.

Run locally:  uv run uvicorn hip.gateway.app:app --reload
In container:  uvicorn hip.gateway.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from hip import __version__
from hip.gateway.api import admin, fhir
from hip.gateway.auth import AuthError, authenticator_from_env
from hip.persistence.db import make_engine, make_sessionmaker
from hip.security.keymanager import keymanager_from_env


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the DB engine/session factory and authenticator at startup.

    The engine is created lazily-connecting, so building the app never requires a
    reachable database — only routes that actually query one do.
    """
    engine = make_engine()
    app.state.engine = engine
    app.state.session_factory = make_sessionmaker(engine)
    app.state.authenticator = authenticator_from_env()
    app.state.key_manager = keymanager_from_env()
    try:
        yield
    finally:
        await engine.dispose()


async def _auth_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render auth failures as a FHIR OperationOutcome (401/403)."""
    if not isinstance(exc, AuthError):  # pragma: no cover - only registered for AuthError
        raise exc
    body = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": exc.code, "diagnostics": exc.detail}],
    }
    return JSONResponse(body, status_code=exc.status_code, media_type="application/fhir+json")


def create_app() -> FastAPI:
    """Build and configure a Gateway ASGI app."""
    app = FastAPI(
        title="Healthcare Interoperability Platform — Gateway",
        version=__version__,
        summary="HIPAA-aligned HL7 v2 + FHIR (R4/R5) interoperability gateway.",
        lifespan=lifespan,
    )
    app.add_exception_handler(AuthError, _auth_error_handler)
    app.include_router(admin.router)
    app.include_router(fhir.router)
    return app


app = create_app()
