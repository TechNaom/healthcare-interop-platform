"""Integration: the full round trip — HL7 in, FHIR out.

Ingest an ADT over the pipeline into real Postgres, then read the patient back
through the gateway's FHIR API and assert it is well-formed FHIR R4. Uses httpx
against the ASGI app (no network server needed); the app's session factory is
pointed at the test database. Synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import pytest

from hip.gateway.app import create_app
from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.parser import parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.phi_repo import PhiRepository

pytestmark = pytest.mark.integration


async def _ingest_then_read_fhir(url: str, adt: str) -> tuple[int, dict[str, Any]]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)

    # Ingest an ADT and capture the patient's canonical id.
    bundle = map_message(parse(adt))
    assert bundle.patient is not None
    patient_id: UUID = bundle.patient.canonical_id
    async with session_factory() as session:
        await PhiRepository(session).save_bundle(bundle)
        await session.commit()

    # Build the app, point it at the test DB (bypass lifespan), read via FHIR API.
    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/fhir/Patient/{patient_id}")
        missing = await client.get(f"/fhir/Patient/{UUID(int=0)}")

    await engine.dispose()
    assert missing.status_code == 404
    assert missing.json()["resourceType"] == "OperationOutcome"
    return resp.status_code, resp.json()


def test_hl7_in_fhir_out(clean_db: str, adt_a01: str) -> None:
    status, body = _run(clean_db, adt_a01)
    assert status == 200
    assert body["resourceType"] == "Patient"
    assert body["name"][0]["family"] == "DOE"
    assert body["gender"] == "female"
    assert body["birthDate"] == "1980-01-01"
    # identifier carries the source MRN + assigning authority.
    assert any(i["value"] == "MRN12345" for i in body["identifier"])


def _run(url: str, adt: str) -> tuple[int, dict[str, Any]]:
    return asyncio.run(_ingest_then_read_fhir(url, adt))
