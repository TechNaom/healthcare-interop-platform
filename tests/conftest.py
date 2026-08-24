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

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Repository root — tier tests resolve fixtures/goldens relative to this."""
    return Path(__file__).resolve().parents[1]
