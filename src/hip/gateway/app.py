"""FastAPI application factory for the Integration Gateway.

Assembles the outward API surface (docs/DESIGN.md 1): admin/health now, FHIR
routes as they land (Phase 6-7). A factory (``create_app``) rather than a
module-level singleton keeps tests able to build isolated app instances, while
``app`` at module scope is the ASGI target for uvicorn / the container.

Run locally:  uv run uvicorn hip.gateway.app:app --reload
In container:  uvicorn hip.gateway.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from hip import __version__
from hip.gateway.api import admin, fhir, ingest
from hip.gateway.auth import AuthError, authenticator_from_env
from hip.gateway.ratelimit import rate_limiter_from_env
from hip.observability.logging import configure_logging
from hip.observability.metrics import RequestMetrics, configure_metrics
from hip.observability.tracing import configure_tracing, get_tracer
from hip.persistence.db import make_engine, make_sessionmaker
from hip.security.blind_index import blind_indexer_from_env
from hip.security.keymanager import keymanager_from_env

# Liveness/readiness/schema/metrics endpoints are not throttled or metered.
_UNMETERED = frozenset({"/healthz", "/readyz", "/metrics", "/openapi.json", "/docs", "/redoc"})

_tracer = get_tracer("hip.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the DB engine/session factory and authenticator at startup.

    The engine is created lazily-connecting, so building the app never requires a
    reachable database — only routes that actually query one do.
    """
    configure_logging()
    configure_metrics()
    configure_tracing(service_name="hip.gateway")
    engine = make_engine()
    app.state.engine = engine
    app.state.session_factory = make_sessionmaker(engine)
    app.state.authenticator = authenticator_from_env()
    app.state.key_manager = keymanager_from_env()
    app.state.blind_indexer = blind_indexer_from_env()
    app.state.rate_limiter = rate_limiter_from_env()
    app.state.request_metrics = RequestMetrics()
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

    @app.middleware("http")
    async def _observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path = request.url.path
        metered = path not in _UNMETERED
        start = time.perf_counter()

        # A server span per request. Attributes carry the route TEMPLATE and
        # status only (bounded cardinality; never a PHI value or concrete id).
        with _tracer.start_as_current_span(f"{request.method} {path}") as span:
            limiter = getattr(request.app.state, "rate_limiter", None)
            if (
                limiter is not None
                and metered
                and not await limiter.allow(request.client.host if request.client else "anonymous")
            ):
                body = {
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "severity": "error",
                            "code": "throttled",
                            "diagnostics": "rate limit exceeded",
                        }
                    ],
                }
                response: Response = JSONResponse(
                    body, status_code=429, media_type="application/fhir+json"
                )
            else:
                response = await call_next(request)

            route = request.scope.get("route")
            route_template = getattr(route, "path", None) or "unmatched"
            span.set_attribute("http.method", request.method)
            span.set_attribute("http.route", route_template)
            span.set_attribute("http.status_code", response.status_code)

            rm = getattr(request.app.state, "request_metrics", None)
            if rm is not None and metered:
                rm.record(
                    method=request.method,
                    route=route_template,
                    status=response.status_code,
                    duration_s=time.perf_counter() - start,
                )
        return response

    app.include_router(admin.router)
    app.include_router(fhir.router)
    app.include_router(ingest.router)
    return app


app = create_app()
