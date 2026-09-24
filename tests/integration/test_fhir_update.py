"""Integration: FHIR update (PUT) — the 'U' in CRUD, end to end.

Create a Patient, PUT a modified version to its id, and read it back to confirm
the change persisted (encrypted upsert). Also covers the RBAC (403 without
``fhir:write``) and validation (400 on invalid FHIR) paths. httpx against the
ASGI app; real Postgres. Synthetic data only (ADR-005).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import jwt
import pytest

from hip.gateway.app import create_app
from hip.gateway.auth import TokenAuthenticator
from hip.persistence.db import make_engine, make_sessionmaker
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration

_SECRET = "fhir-update-integration-secret-32bytes!!"  # noqa: S105
_FHIR_JSON = "application/fhir+json"


def _auth_header(*roles: str) -> dict[str, str]:
    token = jwt.encode({"sub": "editor", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")
    return {"Authorization": f"Bearer {token}"}


def _patient(family: str) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "identifier": [{"system": "HOSP", "value": "MRN-UP"}],
        "name": [{"family": family, "given": ["JANE"]}],
        "gender": "female",
        "birthDate": "1980-01-01",
    }


async def _scenario(url: str, km: KeyManager, indexer: BlindIndexer) -> dict[str, httpx.Response]:
    engine = make_engine(url)
    app = create_app()
    app.state.engine = engine
    app.state.session_factory = make_sessionmaker(engine)
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km
    app.state.blind_indexer = indexer

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        write = _auth_header("fhir:write", "phi:full")
        read = _auth_header("fhir:read", "phi:full")

        created = await client.post("/fhir/Patient", json=_patient("DOE"), headers=write)
        location = created.headers["Location"]  # /fhir/Patient/{id}
        patient_id = location.rsplit("/", 1)[-1]

        responses = {
            "created": created,
            "forbidden": await client.put(
                location, json=_patient("SMITH"), headers=_auth_header("fhir:read")
            ),
            "invalid": await client.put(
                location, json={"resourceType": "Patient", "name": "not-a-list"}, headers=write
            ),
            "updated": await client.put(location, json=_patient("SMITH"), headers=write),
            "read_back": await client.get(f"/fhir/Patient/{patient_id}", headers=read),
        }
    await engine.dispose()
    return responses


def test_fhir_update_upserts_and_is_readable(
    clean_db: str, key_manager: KeyManager, blind_indexer: BlindIndexer
) -> None:
    r = asyncio.run(_scenario(clean_db, key_manager, blind_indexer))

    assert r["created"].status_code == 201
    assert r["forbidden"].status_code == 403  # RBAC: needs fhir:write
    assert r["invalid"].status_code == 400  # OperationOutcome on bad FHIR
    assert r["invalid"].json()["resourceType"] == "OperationOutcome"

    assert r["updated"].status_code == 200
    assert r["updated"].headers["content-type"].startswith(_FHIR_JSON)

    # The change is durable: the read-back reflects the updated family name.
    read_back = r["read_back"].json()
    assert r["read_back"].status_code == 200
    assert read_back["name"][0]["family"] == "SMITH"
