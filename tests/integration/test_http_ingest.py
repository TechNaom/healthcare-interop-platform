"""Integration: HL7 in over HTTP, FHIR out — the second transport, end to end.

POST a synthetic ADT to ``/hl7/v2`` (the HTTP ingestion transport), assert the
HL7 ``AA`` ACK comes back, then find the patient again through the FHIR search
API — proving the HTTP transport funnels into the same encrypted-persist pipeline
as MLLP. Also covers the 401 (no token) and 403 (wrong role) paths. Uses httpx
against the ASGI app (no network server). Synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio

import httpx
import jwt
import pytest

from hip.gateway.app import create_app
from hip.gateway.auth import TokenAuthenticator
from hip.persistence.db import make_engine, make_sessionmaker
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration

_SECRET = "http-ingest-integration-secret-32bytes!!"  # noqa: S105


def _auth_header(*roles: str) -> dict[str, str]:
    token = jwt.encode({"sub": "gw", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")
    return {"Authorization": f"Bearer {token}"}


async def _scenario(
    url: str, adt: str, km: KeyManager, indexer: BlindIndexer
) -> dict[str, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km
    app.state.blind_indexer = indexer

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = {
            "no_token": await client.post("/hl7/v2", content=adt),
            "wrong_role": await client.post(
                "/hl7/v2", content=adt, headers=_auth_header("fhir:read")
            ),
            "accepted": await client.post(
                "/hl7/v2", content=adt, headers=_auth_header("hl7:ingest")
            ),
            # The message is now persisted — find it back through FHIR search.
            "search": await client.get(
                "/fhir/Patient?identifier=HOSP|MRN12345",
                headers=_auth_header("fhir:read", "phi:full"),
            ),
        }
    await engine.dispose()
    return responses


def test_http_ingest_persists_and_is_searchable(
    clean_db: str, adt_a01: str, key_manager: KeyManager, blind_indexer: BlindIndexer
) -> None:
    r = asyncio.run(_scenario(clean_db, adt_a01, key_manager, blind_indexer))

    assert r["no_token"].status_code == 401
    assert r["wrong_role"].status_code == 403

    # Accepted: HTTP 200 + an HL7 AA ACK body.
    assert r["accepted"].status_code == 200
    assert r["accepted"].headers["content-type"].startswith("application/hl7-v2")
    assert "MSA|AA" in r["accepted"].text

    # The patient POSTed over HTTP is now retrievable via the FHIR blind-index search.
    bundle = r["search"].json()
    assert r["search"].status_code == 200
    assert bundle["resourceType"] == "Bundle"
    assert bundle["total"] >= 1
