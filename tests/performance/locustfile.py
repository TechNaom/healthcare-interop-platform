# mypy: ignore-errors
# ^ locust is a perf-only optional dependency (extras=perf), absent from the dev
#   env and shipping no type stubs. This is a runnable load script, not shipped
#   code, so it is deliberately outside strict typing. Run via locust, not mypy.
"""Locust load-test definition — performance tier (SRS 7.1 targets).

Run against a deployed stack, NOT via pytest:

    uv sync --extra perf
    uv run locust -f tests/performance/locustfile.py --host http://localhost:8000

SRS 7.1 provisional targets for the Python-only build (re-benchmark, don't
assume — ADR-006): ~50 msg/s HL7, ~200 req/s FHIR, P95 < 300ms. Load data is the
generated synthetic population (hip.synthetic) — never real PHI (ADR-005). Set
HIP_JWT_SECRET so tasks can mint scoped tokens against the running stack.
"""

from __future__ import annotations

import itertools
import os

import jwt
from locust import HttpUser, between, task

from hip.synthetic import SyntheticPopulation

_SECRET = os.environ.get("HIP_JWT_SECRET", "")


def _token(*roles: str) -> str:
    return jwt.encode({"sub": "loadtest", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")


class GatewayUser(HttpUser):
    """Simulated FHIR API client driven by the synthetic population."""

    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        # Each simulated user seeds from a distinct slice of the population so
        # created identifiers don't collide across users.
        self._population = SyntheticPopulation(seed=hash(self) & 0xFFFF)
        self._counter = itertools.count()
        self._headers = {"Authorization": f"Bearer {_token('fhir:read', 'fhir:write', 'phi:full')}"}

    @task
    def healthz(self) -> None:
        """Liveness probe (unauthenticated)."""
        self.client.get("/healthz")

    @task(3)
    def create_read_search_patient(self) -> None:
        """Create a synthetic Patient, read it back, and search by identifier."""
        person = self._population.person(next(self._counter))
        created = self.client.post(
            "/fhir/Patient", json=self._population.fhir_patient(person), headers=self._headers
        )
        location = created.headers.get("Location")
        if location:
            self.client.get(location, headers=self._headers, name="/fhir/Patient/{id}")
        self.client.get(
            "/fhir/Patient",
            params={"identifier": f"HOSP|{person.mrn}"},
            headers=self._headers,
            name="/fhir/Patient?identifier",
        )
