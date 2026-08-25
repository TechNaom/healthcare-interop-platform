"""Shared pytest fixtures and helpers across all test tiers.

Tier layout (see docs/TEST_STRATEGY.md):
    tests/unit/         fast, in-process, no I/O                 -m unit
    tests/integration/  2+ components vs real containers         -m integration
    tests/regression/   locks shipped behavior against change    -m regression
    tests/performance/  throughput/latency vs SRS 7.1            -m performance
    tests/uat/          acceptance scenarios (docs/UAT_PLAN.md)   -m uat

Fixtures that need real infrastructure (Postgres/Keycloak/Vault/MinIO via
testcontainers) are added here as those phases land, so every tier shares one
container-lifecycle definition rather than each re-inventing it.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root — tier tests resolve fixtures/goldens relative to this."""
    return REPO_ROOT


# --------------------------------------------------------------------------- #
# Postgres for integration tests. Shared across integration test modules.
# HIP_TEST_DATABASE_URL -> use that instance (local verification); otherwise
# testcontainers spins one up (CI). Real Postgres, no mocks (TEST_STRATEGY 3).
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    env_url = os.environ.get("HIP_TEST_DATABASE_URL")
    if env_url:
        yield env_url
        return
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16") as pg:
        host = pg.get_container_host_ip()
        port = pg.get_exposed_port(5432)
        yield f"postgresql+asyncpg://{pg.username}:{pg.password}@{host}:{port}/{pg.dbname}"


@pytest.fixture(scope="session")
def migrated_db(pg_url: str) -> str:
    """Apply the real Alembic migration to the target database (once per session)."""
    env = {**os.environ, "HIP_DATABASE_URL": pg_url}
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    return pg_url


async def _truncate(url: str) -> None:
    from sqlalchemy import text

    from hip.persistence.db import make_engine

    engine = make_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE phi_resources, audit_events, deid_resources"))
    await engine.dispose()


@pytest.fixture
def clean_db(migrated_db: str) -> str:
    """A migrated DB with empty tables — isolates each integration test."""
    asyncio.run(_truncate(migrated_db))
    return migrated_db


# --------------------------------------------------------------------------- #
# Synthetic HL7 v2 samples — NEVER real PHI (ADR-005). Segment separator is <CR>.
# --------------------------------------------------------------------------- #
def _hl7(*segments: str) -> str:
    return "\r".join(segments) + "\r"


ADT_A01 = _hl7(
    "MSH|^~\\&|SENDAPP|SENDFAC|RECVAPP|RECVFAC|20260825101500||ADT^A01|MSG00001|P|2.5",
    "EVN|A01|20260825101500",
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE^Q||19800101|F",
    "PV1|1|I|WARD^101^A",
)

ORU_R01 = _hl7(
    "MSH|^~\\&|LAB|LABFAC|RECVAPP|RECVFAC|20260825101500||ORU^R01|MSG00002|P|2.5",
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE^Q||19800101|F",
    "OBR|1|PLAC1|FILL1|2339-0^Glucose^LN",
    "OBX|1|NM|2339-0^Glucose^LN||5.4|mmol/L|3.9-5.8|N|||F",
)

# Structurally valid but a message type we don't accept.
MDM_T01 = _hl7(
    "MSH|^~\\&|DOC|DOCFAC|RECVAPP|RECVFAC|20260825101500||MDM^T01|MSG00003|P|2.5",
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE^Q||19800101|F",
)

# Malformed: does not start with MSH.
MALFORMED_NO_MSH = "PID|1||MRN12345\rEVN|A01\r"


@pytest.fixture
def adt_a01() -> str:
    return ADT_A01


@pytest.fixture
def oru_r01() -> str:
    return ORU_R01


@pytest.fixture
def mdm_t01() -> str:
    return MDM_T01


@pytest.fixture
def malformed_no_msh() -> str:
    return MALFORMED_NO_MSH
