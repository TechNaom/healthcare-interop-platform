"""Compliance: DB-level enforcement of audit immutability + store separation.

These prove the guarantees hold even against a misbehaving application: acting as
the least-privilege application role, UPDATE/DELETE on the audit ledger are
refused by Postgres; acting as the analytics role, the PHI store is unreadable.
The grants mirror sql/least_privilege.sql. Real Postgres only (docs/TEST_STRATEGY.md 4).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from hip.persistence.db import make_engine

pytestmark = [pytest.mark.integration, pytest.mark.compliance]

_PW = "compliancetestpw"  # noqa: S105 - ephemeral test role password


async def _create_login_role(owner_url: str, role: str, grants: list[str]) -> None:
    engine = make_engine(owner_url)
    async with engine.connect() as conn:
        auto = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await auto.execute(text(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{_PW}'"))
        await auto.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
        for grant in grants:
            await auto.execute(text(grant))
    await engine.dispose()


def _role_url(owner_url: str, role: str) -> str:
    url = make_url(owner_url).set(username=role, password=_PW)
    return url.render_as_string(hide_password=False)


async def _audit_immutability(owner_url: str) -> None:
    role = f"hip_app_{uuid4().hex[:8]}"
    # Append-only grant: SELECT + INSERT, but no UPDATE/DELETE on the ledger.
    await _create_login_role(owner_url, role, [f'GRANT SELECT, INSERT ON audit_events TO "{role}"'])
    app = make_engine(_role_url(owner_url, role))
    try:
        # INSERT is allowed.
        async with app.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_events (id, occurred_at, action, resource_type, actor) "
                    "VALUES (:id, now(), 'read', 'Patient', 'tester')"
                ),
                {"id": uuid4()},
            )
        # UPDATE and DELETE are refused by the database.
        with pytest.raises(ProgrammingError):
            async with app.begin() as conn:
                await conn.execute(text("UPDATE audit_events SET actor = 'tamper'"))
        with pytest.raises(ProgrammingError):
            async with app.begin() as conn:
                await conn.execute(text("DELETE FROM audit_events"))
    finally:
        await app.dispose()


def test_audit_log_is_immutable_at_db_level(migrated_db: str) -> None:
    asyncio.run(_audit_immutability(migrated_db))


async def _store_separation(owner_url: str) -> None:
    role = f"hip_analytics_{uuid4().hex[:8]}"
    # Analytics can read the de-identified store only.
    await _create_login_role(owner_url, role, [f'GRANT SELECT ON deid_resources TO "{role}"'])
    analytics = make_engine(_role_url(owner_url, role))
    try:
        # De-identified store is readable.
        async with analytics.begin() as conn:
            await conn.execute(text("SELECT count(*) FROM deid_resources"))
        # The PHI store is not reachable at all.
        with pytest.raises(ProgrammingError):
            async with analytics.begin() as conn:
                await conn.execute(text("SELECT count(*) FROM phi_resources"))
    finally:
        await analytics.dispose()


def test_analytics_role_cannot_read_phi(migrated_db: str) -> None:
    asyncio.run(_store_separation(migrated_db))
