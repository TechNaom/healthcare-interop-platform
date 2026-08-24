# mypy: ignore-errors
# ^ locust is a perf-only optional dependency (extras=perf), absent from the dev
#   env and shipping no type stubs. This is a runnable load script, not shipped
#   code, so it is deliberately outside strict typing. Run via locust, not mypy.
"""Locust load-test definition — performance tier (SRS 7.1 targets).

Run against a deployed stack, NOT via pytest:

    uv sync --extra perf
    uv run locust -f tests/performance/locustfile.py --host http://localhost:8000

SRS 7.1 provisional targets for the Python-only build (re-benchmark, don't
assume — ADR-006): ~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms. These tasks are
skeletons hitting endpoints that exist from Phase 1 (health) onward; FHIR/HL7
load tasks are filled in as those endpoints land (Phase 6-7). Load data is
generated Synthea population only — never real PHI (ADR-005).
"""

from __future__ import annotations

from locust import HttpUser, between, task


class GatewayUser(HttpUser):
    """Simulated FHIR API client."""

    wait_time = between(0.1, 0.5)

    @task
    def healthz(self) -> None:
        """Liveness probe — the first endpoint available (Phase 1)."""
        self.client.get("/healthz")

    # TODO(Phase 6-7): add FHIR read/search/create tasks against scoped tokens,
    # driven by the generated Synthea population, and assert P95 < 300ms.
