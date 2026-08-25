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
