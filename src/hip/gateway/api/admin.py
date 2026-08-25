"""Admin API: health/readiness (and, later, routing config + metrics).

Maps to ``gateway.api.admin`` in docs/DESIGN.md 1. ``/healthz`` (liveness) and
``/readyz`` (readiness) are the probes container/K8s orchestration needs
(docs/TECH_STACK.md "Where Kubernetes would enter"). Liveness answers "is the
process up"; readiness answers "can it serve traffic" — the latter will grow
dependency checks (DB, Keycloak) as those land, and report 503 until they pass.
"""

from __future__ import annotations

from fastapi import APIRouter

from hip import __version__

router = APIRouter(tags=["admin"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness: the process is up and serving. No dependency checks."""
    return {"status": "ok", "version": __version__}


@router.get("/readyz")
def readyz() -> dict[str, str]:
    """Readiness: safe to receive traffic.

    No external dependencies are wired yet, so this is currently equivalent to
    liveness. As persistence/identity land, this grows real checks and returns
    503 until they pass — that is the intended shape, not an afterthought.
    """
    return {"status": "ready", "version": __version__, "checks": "none-yet"}
