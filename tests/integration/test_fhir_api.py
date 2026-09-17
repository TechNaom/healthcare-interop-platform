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
            "ok": await client.get(path, headers=_auth_header("fhir:read", "phi:full")),
            "limited": await client.get(path, headers=_auth_header("fhir:read")),
            "missing_token": await client.get(path),
            "wrong_role": await client.get(path, headers=_auth_header("billing")),
            "not_found": await client.get(
                f"/fhir/Patient/{UUID(int=0)}", headers=_auth_header("fhir:read", "phi:full")
            ),
        }
    await engine.dispose()
    return responses


def test_fhir_read_enforces_auth_and_returns_patient(
    clean_db: str, adt_a01: str, key_manager: KeyManager
) -> None:
    r = asyncio.run(_scenario(clean_db, adt_a01, key_manager))

    # Full-access clinician -> the complete FHIR Patient.
    assert r["ok"].status_code == 200
    body: dict[str, Any] = r["ok"].json()
    assert body["resourceType"] == "Patient"
    assert body["name"][0]["family"] == "DOE"
    assert body["gender"] == "female"
    assert any(i["value"] == "MRN12345" for i in body["identifier"])
    assert "address" in body  # full access includes contact info

    # Minimum-necessary: without phi:full, demographics only — no contact info.
    assert r["limited"].status_code == 200
    limited: dict[str, Any] = r["limited"].json()
    assert limited["name"][0]["family"] == "DOE"  # matching demographics kept
    assert any(i["value"] == "MRN12345" for i in limited["identifier"])
    assert "address" not in limited  # contact info removed, not blanked
    assert "telecom" not in limited

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
        headers = _auth_header("fhir:read", "phi:full")
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


_NEW_PATIENT = {
    "resourceType": "Patient",
    "identifier": [{"system": "HOSP", "value": "MRN-NEW", "type": {"coding": [{"code": "MR"}]}}],
    "name": [{"use": "official", "family": "ROE", "given": ["RICH"]}],
    "gender": "male",
    "birthDate": "1975-03-09",
}


async def _create_then_read(
    url: str, km: KeyManager
) -> tuple[httpx.Response, httpx.Response, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/fhir/Patient", json=_NEW_PATIENT, headers=_auth_header("fhir:write")
        )
        location = created.headers.get("Location", "")
        read_back = await client.get(location, headers=_auth_header("fhir:read", "phi:full"))
        forbidden = await client.post(
            "/fhir/Patient", json=_NEW_PATIENT, headers=_auth_header("fhir:read")
        )  # read role can't write
    await engine.dispose()
    return created, read_back, forbidden


def test_create_patient_then_read_back(clean_db: str, key_manager: KeyManager) -> None:
    created, read_back, forbidden = asyncio.run(_create_then_read(clean_db, key_manager))

    assert created.status_code == 201
    assert created.headers["Location"].startswith("/fhir/Patient/")
    assert created.json()["name"][0]["family"] == "ROE"

    # The created resource is retrievable and encrypted-at-rest round-trips.
    assert read_back.status_code == 200
    assert read_back.json()["name"][0]["family"] == "ROE"
    assert any(i["value"] == "MRN-NEW" for i in read_back.json()["identifier"])

    # Write requires the write role.
    assert forbidden.status_code == 403


async def _create_then_search(
    url: str, km: KeyManager, bi: object
) -> tuple[httpx.Response, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km
    app.state.blind_indexer = bi

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/fhir/Patient", json=_NEW_PATIENT, headers=_auth_header("fhir:write"))
        hit = await client.get(
            "/fhir/Patient?identifier=HOSP|MRN-NEW", headers=_auth_header("fhir:read", "phi:full")
        )
        miss = await client.get(
            "/fhir/Patient?identifier=NOPE", headers=_auth_header("fhir:read", "phi:full")
        )
    await engine.dispose()
    return hit, miss


def test_search_patient_by_identifier(
    clean_db: str, key_manager: KeyManager, blind_indexer: object
) -> None:
    hit, miss = asyncio.run(_create_then_search(clean_db, key_manager, blind_indexer))

    assert hit.status_code == 200
    bundle = hit.json()
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "searchset"
    assert bundle["total"] == 1
    assert bundle["entry"][0]["resource"]["name"][0]["family"] == "ROE"

    # A non-matching identifier returns an empty searchset (not a 404).
    assert miss.status_code == 200
    assert miss.json()["total"] == 0


_NEW_ENCOUNTER: dict[str, Any] = {
    "resourceType": "Encounter",
    "status": "in-progress",
    "class": {"code": "IMP", "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode"},
    "identifier": [{"value": "VISIT-1"}],
}

_NEW_OBSERVATION: dict[str, Any] = {
    "resourceType": "Observation",
    "status": "final",
    "code": {"coding": [{"code": "2339-0", "system": "http://loinc.org", "display": "Glucose"}]},
    "valueQuantity": {"value": 5.4, "unit": "mmol/L"},
}


async def _create_read(url: str, km: KeyManager, path: str, body: dict[str, Any]) -> httpx.Response:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km
    app.state.blind_indexer = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(path, json=body, headers=_auth_header("fhir:write"))
        location = created.headers.get("Location", "")
        assert created.status_code == 201, created.text
        read = await client.get(location, headers=_auth_header("fhir:read", "phi:full"))
    await engine.dispose()
    return read


def test_create_encounter_then_read(clean_db: str, key_manager: KeyManager) -> None:
    read = asyncio.run(_create_read(clean_db, key_manager, "/fhir/Encounter", _NEW_ENCOUNTER))
    assert read.status_code == 200
    assert read.json()["resourceType"] == "Encounter"
    assert read.json()["status"] == "in-progress"


def test_create_observation_then_read(clean_db: str, key_manager: KeyManager) -> None:
    read = asyncio.run(_create_read(clean_db, key_manager, "/fhir/Observation", _NEW_OBSERVATION))
    assert read.status_code == 200
    assert read.json()["resourceType"] == "Observation"
    assert read.json()["valueQuantity"]["value"] == 5.4


_NEW_SERVICE_REQUEST: dict[str, Any] = {
    "resourceType": "ServiceRequest",
    "status": "active",
    "intent": "order",
    "subject": {"display": "unknown"},
    "code": {"coding": [{"code": "2339-0", "system": "http://loinc.org", "display": "Glucose"}]},
    "identifier": [{"value": "PLAC-9", "type": {"coding": [{"code": "PLAC"}]}}],
}


def test_create_service_request_then_read(clean_db: str, key_manager: KeyManager) -> None:
    read = asyncio.run(
        _create_read(clean_db, key_manager, "/fhir/ServiceRequest", _NEW_SERVICE_REQUEST)
    )
    assert read.status_code == 200
    body = read.json()
    assert body["resourceType"] == "ServiceRequest"
    assert body["status"] == "active"
    assert body["intent"] == "order"
    assert body["code"]["coding"][0]["code"] == "2339-0"


async def _ingest_orm_then_read_sr(url: str, km: KeyManager) -> httpx.Response:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    orm = (
        "MSH|^~\\&|OE|OF|R|RF|20260825101500||ORM^O01|MID-ORM|P|2.5\r"
        "PID|1||MRN1^^^HOSP^MR||DOE^JANE||19800101|F\r"
        "ORC|NW|PLAC1|FILL1\r"
        "OBR|1|PLAC1|FILL1|2339-0^Glucose^LN\r"
    )
    bundle = map_message(parse(orm))
    assert bundle.orders
    order_id = bundle.orders[0].canonical_id
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
        resp = await client.get(
            f"/fhir/ServiceRequest/{order_id}", headers=_auth_header("fhir:read", "phi:full")
        )
    await engine.dispose()
    return resp


def test_ingested_order_reads_as_service_request(clean_db: str, key_manager: KeyManager) -> None:
    resp = asyncio.run(_ingest_orm_then_read_sr(clean_db, key_manager))
    assert resp.status_code == 200
    assert resp.json()["resourceType"] == "ServiceRequest"
    assert resp.json()["intent"] == "order"
