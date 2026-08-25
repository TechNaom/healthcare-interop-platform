"""Integration: mapped bundles persist to real Postgres, with audit, via migrations.

Real Postgres — no mocks (docs/TEST_STRATEGY.md 3). Two ways to get one:
* ``HIP_TEST_DATABASE_URL`` set -> use that instance (how we verify locally,
  pointing at a Postgres started with docker);
* otherwise spin one up with testcontainers (how CI runs it).

Schema is created by running the real Alembic migration (``alembic upgrade
head``), so migrations are exercised end-to-end, not bypassed. Synthetic HL7
only (ADR-005).
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
from hip.persistence.models import AuditEvent, PhiResource
from hip.persistence.phi_repo import PhiRepository

pytestmark = pytest.mark.integration


async def _persist_read_audit(url: str, adt: str) -> None:
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    bundle = map_message(parse(adt))
    assert bundle.patient is not None

    # Persist the mapped bundle (patient + encounter) in one transaction.
    async with session_factory() as session:
        repo = PhiRepository(session)
        saved = await repo.save_bundle(bundle)
        await session.commit()
    assert len(saved) == 2  # Patient + Encounter

    # Read the patient back through the repo (emits a read audit).
    async with session_factory() as session:
        repo = PhiRepository(session)
        row = await repo.get(bundle.patient.canonical_id, actor="test:reader")
        await session.commit()
        assert row is not None
        assert row.resource_type == "Patient"
        assert row.payload["name"][0]["family"] == "DOE"

    # Every write and the read produced audit entries (>= 2 creates + 1 read).
    async with session_factory() as session:
        total = await session.scalar(select(func.count()).select_from(AuditEvent))
        creates = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "create")
        )
        reads = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "read")
        )
    assert creates == 2
    assert reads == 1
    assert total == 3

    # Sanity: exactly the two resources are stored.
    async with session_factory() as session:
        stored = await session.scalar(select(func.count()).select_from(PhiResource))
    assert stored == 2

    await engine.dispose()


def test_bundle_persists_with_audit(clean_db: str, adt_a01: str) -> None:
    asyncio.run(_persist_read_audit(clean_db, adt_a01))


async def _socket_to_db(url: str, adt: str) -> int:
    """Full loop: HL7 over an MLLP socket -> stored in Postgres."""
    engine = make_engine(url)
    session_factory = make_sessionmaker(engine)
    listener = MLLPListener(host="127.0.0.1", port=0, session_factory=session_factory)
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


def test_ingested_message_is_persisted_end_to_end(clean_db: str, adt_a01: str) -> None:
    """An HL7 message sent over the wire lands in the store — the full ingest loop."""
    stored = asyncio.run(_socket_to_db(clean_db, adt_a01))
    assert stored == 2  # Patient + Encounter
