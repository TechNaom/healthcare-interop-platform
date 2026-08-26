"""Integration: mapped bundles persist to real Postgres — encrypted, audited.

Real Postgres — no mocks (docs/TEST_STRATEGY.md 3). Schema is created by running
the real Alembic migrations, so they are exercised end-to-end. PHI is encrypted
at rest by the KeyManager. Synthetic HL7 only (ADR-005).
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.listener import MLLPListener
from hip.messaging.hl7.mllp import MLLPBuffer, wrap
from hip.messaging.hl7.parser import parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.deid_repo import DeidRepository
from hip.persistence.models import AuditEvent, DeidResource, PhiResource
from hip.persistence.phi_repo import PhiRepository
from hip.security.deid import deidentify_patient
from hip.security.keymanager import KeyManager

pytestmark = pytest.mark.integration


async def _persist_read_audit(url: str, adt: str, km: KeyManager) -> None:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    bundle = map_message(parse(adt))
    assert bundle.patient is not None

    async with session_factory() as session:
        saved = await PhiRepository(session, km).save_bundle(bundle)
        await session.commit()
    assert len(saved) == 2  # Patient + Encounter

    async with session_factory() as session:
        stored = await PhiRepository(session, km).get(
            bundle.patient.canonical_id, actor="test:reader"
        )
        await session.commit()
        assert stored is not None
        assert stored.resource_type == "Patient"
        assert stored.payload["name"][0]["family"] == "DOE"  # decrypts correctly

    async with session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(AuditEvent))
        creates = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "create")
        )
        reads = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "read")
        )
    assert (creates, reads, total) == (2, 1, 3)
    await engine.dispose()


def test_bundle_persists_with_audit(clean_db: str, adt_a01: str, key_manager: KeyManager) -> None:
    asyncio.run(_persist_read_audit(clean_db, adt_a01, key_manager))


async def _phi_encrypted_at_rest(url: str, adt: str, km: KeyManager) -> bytes:
    """Persist a patient and return the raw stored ciphertext bytes."""
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    bundle = map_message(parse(adt))
    async with session_factory() as session:
        await PhiRepository(session, km).save_bundle(bundle)
        await session.commit()
    async with session_factory() as session:
        raw = await session.scalar(
            select(PhiResource.payload_ciphertext).where(PhiResource.resource_type == "Patient")
        )
    await engine.dispose()
    assert raw is not None
    return raw


def test_phi_unreadable_at_rest(clean_db: str, adt_a01: str, key_manager: KeyManager) -> None:
    """The raw at-rest bytes contain no plaintext PHI (encryption verified, not just configured)."""
    raw = asyncio.run(_phi_encrypted_at_rest(clean_db, adt_a01, key_manager))
    assert b"DOE" not in raw
    assert b"MRN12345" not in raw
    # And it round-trips back through the KeyManager.
    assert b"DOE" in key_manager.decrypt(raw)


async def _socket_to_db(url: str, adt: str, km: KeyManager) -> int:
    """Full loop: HL7 over an MLLP socket -> encrypted in Postgres."""
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    listener = MLLPListener(
        host="127.0.0.1", port=0, session_factory=session_factory, key_manager=km
    )
    server = await listener.start()
    assert server.sockets
    port = server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(wrap(adt))
        await writer.drain()
        buf = MLLPBuffer()
        acks: list[str] = []
        while not acks:
            acks.extend(buf.feed(await asyncio.wait_for(reader.read(4096), timeout=5)))
        assert "MSA|AA" in acks[0]  # accepted
    finally:
        writer.close()
        server.close()
        await server.wait_closed()

    async with session_factory() as session:
        stored = await session.scalar(select(func.count()).select_from(PhiResource))
    await engine.dispose()
    return stored or 0


def test_ingested_message_is_persisted_end_to_end(
    clean_db: str, adt_a01: str, key_manager: KeyManager
) -> None:
    """An HL7 message sent over the wire lands in the store — the full ingest loop."""
    stored = asyncio.run(_socket_to_db(clean_db, adt_a01, key_manager))
    assert stored == 2  # Patient + Encounter


async def _deid_after_ingest(url: str, adt: str, km: KeyManager) -> dict[str, object]:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    bundle = map_message(parse(adt))
    async with session_factory() as session:
        await PhiRepository(session, km).save_bundle(bundle)
        assert bundle.patient is not None
        await DeidRepository(session).save(deidentify_patient(bundle.patient))
        await session.commit()

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(DeidResource))
        row = (await session.execute(select(DeidResource))).scalar_one()
    await engine.dispose()
    return {"count": count, "payload": row.payload}


def test_deidentified_copy_stored_without_phi(
    clean_db: str, adt_a01: str, key_manager: KeyManager
) -> None:
    """Ingest produces a de-identified Patient in the separate store, carrying no PHI."""
    result = asyncio.run(_deid_after_ingest(clean_db, adt_a01, key_manager))
    assert result["count"] == 1
    payload = result["payload"]
    assert isinstance(payload, dict)
    assert not payload.get("name")
    assert not payload.get("identifiers")
    assert payload.get("account_number") is None
    assert not payload.get("telecom")
