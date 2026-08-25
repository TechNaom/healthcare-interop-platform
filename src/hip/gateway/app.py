"""FastAPI application factory for the Integration Gateway.

Assembles the outward API surface (docs/DESIGN.md 1): admin/health now, FHIR
routes as they land (Phase 6-7). A factory (``create_app``) rather than a
module-level singleton keeps tests able to build isolated app instances, while
``app`` at module scope is the ASGI target for uvicorn / the container.

Run locally:  uv run uvicorn hip.gateway.app:app --reload
In container:  uvicorn hip.gateway.app:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI

from hip import __version__
from hip.gateway.api import admin


def create_app() -> FastAPI:
    """Build and configure a Gateway ASGI app."""
    app = FastAPI(
        title="Healthcare Interoperability Platform — Gateway",
        version=__version__,
        summary="HIPAA-aligned HL7 v2 + FHIR (R4/R5) interoperability gateway.",
    )
    app.include_router(admin.router)
    # Phase 6-7: app.include_router(fhir.router, prefix="/fhir")
    return app


app = create_app()
