"""Integration: the full round trip — HL7 in, FHIR out, with auth enforced.

Ingest an ADT over the pipeline into real Postgres, then read the patient back
through the gateway's FHIR API and assert it is well-formed FHIR R4. The endpoint
requires a valid token with the ``fhir:read`` role, so the test also covers the
401 (no token) and 403 (wrong role) paths. Uses httpx against the ASGI app (no
network server needed). Synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
import jwt
import pytest

from hip.gateway.app import create_app
from hip.gateway.auth import TokenAuthenticator
from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.parser import parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.phi_repo import PhiRepository
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration

_SECRET = "integration-test-secret-padding-32b-minimum"  # noqa: S105


def _token(*roles: str, sub: str = "dr.who") -> str:
    return jwt.encode({"sub": sub, "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")


def _auth_header(*roles: str, sub: str = "dr.who") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(*roles, sub=sub)}"}


async def _scenario(url: str, adt: str, km: KeyManager) -> dict[str, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)

    bundle = map_message(parse(adt))
    assert bundle.patient is not None
    patient_id: UUID = bundle.patient.canonical_id
    async with session_factory() as session:
        await PhiRepository(session, km).save_bundle(bundle)
        await session.commit()

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        path = f"/fhir/Patient/{patient_id}"
        responses = {
            "ok": await client.get(path, headers=_auth_header("fhir:read")),
            "missing_token": await client.get(path),
            "wrong_role": await client.get(path, headers=_auth_header("billing")),
            "not_found": await client.get(
                f"/fhir/Patient/{UUID(int=0)}", headers=_auth_header("fhir:read")
            ),
        }
    await engine.dispose()
    return responses


def test_fhir_read_enforces_auth_and_returns_patient(
    clean_db: str, adt_a01: str, key_manager: KeyManager
) -> None:
    r = asyncio.run(_scenario(clean_db, adt_a01, key_manager))

    # Authenticated with the right role -> the FHIR Patient.
    assert r["ok"].status_code == 200
    body: dict[str, Any] = r["ok"].json()
    assert body["resourceType"] == "Patient"
    assert body["name"][0]["family"] == "DOE"
    assert body["gender"] == "female"
    assert any(i["value"] == "MRN12345" for i in body["identifier"])

    # No token -> 401; wrong role -> 403; both as FHIR OperationOutcome.
    assert r["missing_token"].status_code == 401
    assert r["missing_token"].json()["resourceType"] == "OperationOutcome"
    assert r["wrong_role"].status_code == 403
    assert r["wrong_role"].json()["resourceType"] == "OperationOutcome"

    # Unknown id (authorized) -> 404 OperationOutcome.
    assert r["not_found"].status_code == 404
    assert r["not_found"].json()["resourceType"] == "OperationOutcome"


async def _read_encounter_and_observation(
    url: str, adt: str, oru: str, km: KeyManager
) -> tuple[httpx.Response, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)

    adt_bundle = map_message(parse(adt))
    oru_bundle = map_message(parse(oru))
    assert adt_bundle.encounter is not None
    assert oru_bundle.observations
    enc_id = adt_bundle.encounter.canonical_id
    obs_id = oru_bundle.observations[0].canonical_id
    async with session_factory() as session:
        repo = PhiRepository(session, km)
        await repo.save_bundle(adt_bundle)
        await repo.save_bundle(oru_bundle)
        await session.commit()

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers = _auth_header("fhir:read")
        enc = await client.get(f"/fhir/Encounter/{enc_id}", headers=headers)
        obs = await client.get(f"/fhir/Observation/{obs_id}", headers=headers)
    await engine.dispose()
    return enc, obs


def test_encounter_and_observation_reads(
    clean_db: str, adt_a01: str, oru_r01: str, key_manager: KeyManager
) -> None:
    enc, obs = asyncio.run(_read_encounter_and_observation(clean_db, adt_a01, oru_r01, key_manager))

    assert enc.status_code == 200
    enc_body = enc.json()
    assert enc_body["resourceType"] == "Encounter"
    assert enc_body["status"] == "in-progress"  # ADT^A01

    assert obs.status_code == 200
    obs_body = obs.json()
    assert obs_body["resourceType"] == "Observation"
    assert obs_body["code"]["coding"][0]["code"] == "2339-0"
    assert obs_body["valueQuantity"]["value"] == 5.4
