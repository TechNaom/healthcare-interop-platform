"""Integration tier — 2+ components against real containers (testcontainers).

Marked ``integration``; runs on every PR once there are components to integrate.
Real Postgres/Keycloak/Vault/MinIO via testcontainers (never mocks — see
docs/TEST_STRATEGY.md section 3). Placeholder until the first cross-component
path exists (ingestion -> canonical -> persistence, Phase 5+).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_ingestion_to_persistence_roundtrip() -> None:
    """Ingested canonical record is retrievable from the PHI store.

    Unblocked when persistence (Phase 9) is reachable from ingestion (Phase 5).
    """
    pytest.skip("Pending Phase 5-9. First real integration path.")
