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
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select

from hip.messaging.canonical.mapper import map_message
from hip.messaging.hl7.parser import parse
from hip.persistence.db import make_engine, make_sessionmaker
from hip.persistence.models import AuditEvent, PhiResource
from hip.persistence.phi_repo import PhiRepository

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pg_url() -> Iterator[str]:
    env_url = os.environ.get("HIP_TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return
    # No external DB provided -> manage one with testcontainers (CI path).
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        yield f"postgresql+asyncpg://{pg.username}:{pg.password}@{host}:{port}/{pg.dbname}"


@pytest.fixture(scope="module")
def migrated_db(pg_url: str) -> str:
    """Apply the Alembic migration to the target database."""
    env = {**os.environ, "HIP_DATABASE_URL": pg_url}
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return pg_url


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


def test_bundle_persists_with_audit(migrated_db: str, adt_a01: str) -> None:
    asyncio.run(_persist_read_audit(migrated_db, adt_a01))
