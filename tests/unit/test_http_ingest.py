"""HTTP HL7 ingestion transport — auth enforcement, no DB.

The ``POST /hl7/v2`` endpoint requires a token with the ``hl7:ingest`` role.
These cases (missing token -> 401, wrong role -> 403, bad encoding -> AR) all
short-circuit before any database access, so they run in-process against the
ASGI app with a lazily-connecting engine that is never actually reached.
Synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio

import httpx
import jwt
import pytest

from hip.gateway.app import create_app
from hip.gateway.auth import TokenAuthenticator
from hip.persistence.db import make_engine, make_sessionmaker
from hip.security.keymanager import FernetKeyManager

pytestmark = pytest.mark.unit

_SECRET = "http-ingest-unit-secret-padding-32bytes"  # noqa: S105
_HL7_MEDIA_TYPE = "application/hl7-v2"


def _app() -> object:
    app = create_app()
    # Lazily-connecting engine: never reached because auth fails first.
    engine = make_engine("postgresql+asyncpg://unused:unused@localhost:1/unused")
    app.state.engine = engine
    app.state.session_factory = make_sessionmaker(engine)
    app.state.authenticator = TokenAuthenticator(secret=_SECRET)
    app.state.key_manager = FernetKeyManager(FernetKeyManager.generate_key())
    return app


def _post(headers: dict[str, str], body: bytes) -> httpx.Response:
    app = _app()

    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/hl7/v2", content=body, headers=headers)

    return asyncio.run(_run())


def _token(*roles: str) -> str:
    return jwt.encode({"sub": "edge", "realm_access": {"roles": list(roles)}}, _SECRET, "HS256")


def test_missing_token_is_401() -> None:
    resp = _post({}, b"MSH|^~\\&|A|B|C|D|20260101||ADT^A01|1|P|2.5\r")
    assert resp.status_code == 401


def test_wrong_role_is_403() -> None:
    headers = {"Authorization": f"Bearer {_token('fhir:read')}"}
    resp = _post(headers, b"MSH|^~\\&|A|B|C|D|20260101||ADT^A01|1|P|2.5\r")
    assert resp.status_code == 403


def test_non_utf8_body_is_rejected_with_nack() -> None:
    headers = {"Authorization": f"Bearer {_token('hl7:ingest')}"}
    resp = _post(headers, b"\xff\xfe not utf-8")
    assert resp.status_code == 422
    assert resp.headers["content-type"].startswith(_HL7_MEDIA_TYPE)
    assert "MSA|AR" in resp.text
