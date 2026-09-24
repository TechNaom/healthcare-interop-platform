"""Integration: ServiceRequest (Order) identifier search via the blind index.

Completes search parity across the core FHIR resources. Persist an ORM-derived
order (placer/filler blind-indexed), then find it through
``GET /fhir/ServiceRequest?identifier=`` — the value is matched against the HMAC
index, never in plaintext. httpx against the ASGI app; real Postgres. Synthetic
data only (ADR-005).
"""

from __future__ import annotations

import asyncio

import httpx
import jwt
import pytest

from hip.gateway.app import create_app
from hip.gateway.auth import TokenAuthenticator
from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.parser import parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.phi_repo import PhiRepository
from hip.security.blind_index import BlindIndexer
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration

_SECRET = "sr-search-integration-secret-32-bytes!!!"  # noqa: S105

_ORM = (
    "MSH|^~\\&|OE|OF|R|RF|20260825101500||ORM^O01|SR-SEARCH|P|2.5\r"
    "PID|1||MRN-SR^^^HOSP^MR||DOE^JANE||19800101|F\r"
    "ORC|NW|PLAC-SR|FILL-SR\r"
    "OBR|1|PLAC-SR|FILL-SR|2339-0^Glucose^LN\r"
)


def _auth_header(*roles: str) -> dict[str, str]:
    token = jwt.encode({"sub": "sr", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")
    return {"Authorization": f"Bearer {token}"}


async def _scenario(url: str, km: KeyManager, indexer: BlindIndexer) -> dict[str, httpx.Response]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    bundle = map_message(parse(_ORM))
    assert bundle.orders
    async with session_factory() as session:
        await PhiRepository(session, km, indexer).save_bundle(bundle)
        await session.commit()

    app = create_app()
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = km
    app.state.blind_indexer = indexer

    read = _auth_header("fhir:read", "phi:full")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = {
            "by_filler": await client.get("/fhir/ServiceRequest?identifier=FILL-SR", headers=read),
            "by_placer": await client.get("/fhir/ServiceRequest?identifier=PLAC-SR", headers=read),
            "miss": await client.get("/fhir/ServiceRequest?identifier=NOPE", headers=read),
        }
    await engine.dispose()
    return responses


def test_service_request_identifier_search(
    clean_db: str, key_manager: KeyManager, blind_indexer: BlindIndexer
) -> None:
    r = asyncio.run(_scenario(clean_db, key_manager, blind_indexer))

    by_filler = r["by_filler"].json()
    assert r["by_filler"].status_code == 200
    assert by_filler["resourceType"] == "Bundle"
    assert by_filler["total"] == 1
    assert by_filler["entry"][0]["resource"]["resourceType"] == "ServiceRequest"

    # Placer number also resolves to the same order.
    assert r["by_placer"].json()["total"] == 1
    # An unknown identifier yields an empty searchset, not an error.
    assert r["miss"].json()["total"] == 0
