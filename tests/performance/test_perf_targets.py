"""Performance tier — asserts the SRS 7.1 latency target for a FHIR read.

Two modes, same assertion (P95 < 300 ms, SRS 7.1 — provisional for the
Python-only build, ADR-006):

- **Against a running stack** (`HIP_PERF_TARGET` set to its base URL, e.g. in the
  scheduled perf workflow): drive reads over the network and measure.
- **In-process** (default, needs a Postgres via `HIP_TEST_DATABASE_URL` or
  testcontainers): drive reads through the ASGI app against real Postgres. This
  makes the tier execute a real assertion on every perf run rather than skipping.

Marked ``performance`` and excluded from the default per-PR run. Synthetic data
only (ADR-005). For sustained-throughput load use the locust script alongside.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from typing import Any

import httpx
import jwt
import pytest

pytestmark = pytest.mark.performance

PERF_TARGET = os.environ.get("HIP_PERF_TARGET")
_HAS_DB = bool(os.environ.get("HIP_TEST_DATABASE_URL"))

# SRS 7.1 provisional target for a FHIR read (re-benchmark, don't assume — ADR-006).
_P95_BUDGET_S = 0.300
_ITERATIONS = 50
_SECRET = "perf-tier-secret-padding-32-bytes-minimum"  # noqa: S105


def _token(*roles: str) -> str:
    return jwt.encode({"sub": "perf", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")


def _p95(samples: list[float]) -> float:
    # ``quantiles(n=100)`` returns the 99 cut points; index 94 is the 95th pct.
    return statistics.quantiles(samples, n=100)[94]


async def _measure(client: httpx.AsyncClient, path: str, headers: dict[str, str]) -> list[float]:
    latencies: list[float] = []
    for _ in range(_ITERATIONS):
        start = time.perf_counter()
        resp = await client.get(path, headers=headers)
        latencies.append(time.perf_counter() - start)
        assert resp.status_code == 200
    return latencies


async def _in_process_scenario() -> list[float]:
    """Seed one patient, then time repeated FHIR reads through the ASGI app."""
    from hip.gateway.app import create_app
    from hip.gateway.auth import TokenAuthenticator
    from hip.messaging.canonical.mapper import map_message
    from hip.messaging.hl7.parser import parse
    from hip.persistence.db import make_engine, make_sessionmaker
    from hip.persistence.phi_repo import PhiRepository
    from hip.security.keymanager import FernetKeyManager

    url = os.environ["HIP_TEST_DATABASE_URL"]
    km = FernetKeyManager(FernetKeyManager.generate_key())
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)

    adt = (
        "MSH|^~\\&|A|B|C|D|20260101||ADT^A01|PERF1|P|2.5\r"
        "PID|1||PERF-MRN^^^HOSP^MR||PERF^PATIENT||19800101|F\r"
    )
    bundle = map_message(parse(adt))
    assert bundle.patient is not None
    patient_id = bundle.patient.canonical_id
    async with session_factory() as session:
        await PhiRepository(session, km).save_bundle(bundle)
        await session.commit()

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km

    headers = {"Authorization": f"Bearer {_token('fhir:read', 'phi:full')}"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _measure(client, f"/fhir/Patient/{patient_id}", headers)  # warm up
        latencies = await _measure(client, f"/fhir/Patient/{patient_id}", headers)
    await engine.dispose()
    return latencies


def _network_scenario() -> list[float]:
    """Time repeated FHIR reads against an already-running stack (HIP_PERF_TARGET)."""

    async def _run() -> list[float]:
        headers = {"Authorization": f"Bearer {_token('fhir:read', 'phi:full')}"}
        async with httpx.AsyncClient(base_url=PERF_TARGET or "") as client:
            # Discover any patient to read via search (stack is pre-seeded).
            search = await client.get(
                "/fhir/Patient?identifier=PERF-MRN", headers=headers, timeout=10
            )
            entries: list[dict[str, Any]] = search.json().get("entry", [])
            assert entries, "perf target has no seeded PERF-MRN patient"
            path = f"/fhir/Patient/{entries[0]['resource']['id']}"
            return await _measure(client, path, headers)

    return asyncio.run(_run())


@pytest.mark.skipif(
    PERF_TARGET is None and not _HAS_DB,
    reason="Needs a running stack (HIP_PERF_TARGET) or a Postgres (HIP_TEST_DATABASE_URL).",
)
def test_fhir_read_p95_under_300ms() -> None:
    """P95 latency for a FHIR read stays under the SRS 7.1 budget (300 ms)."""
    latencies = _network_scenario() if PERF_TARGET else asyncio.run(_in_process_scenario())
    p95 = _p95(latencies)
    assert p95 < _P95_BUDGET_S, f"FHIR read P95 {p95 * 1000:.1f}ms exceeds 300ms (SRS 7.1)"
