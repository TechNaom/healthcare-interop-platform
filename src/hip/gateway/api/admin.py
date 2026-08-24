"""Admin API: routing config, health/readiness, metrics endpoints.

Maps to ``gateway.api.admin`` in docs/DESIGN.md section 1. The ``/healthz`` and
``/readyz`` probes required for container liveness/readiness (docs/TECH_STACK.md
"Where Kubernetes would enter") are served from here in Phase 1.
"""
