"""UAT tier — executable checks behind the acceptance scenarios in docs/UAT_PLAN.md.

User Acceptance Testing here is a **release-candidate gate**, not a per-PR check.
Each scenario in docs/UAT_PLAN.md (UAT-01, UAT-02, ...) has a matching test that
drives the system the way an end user / integrating team would, through public
interfaces only. They are marked ``uat`` and excluded from the default run;
they execute against a release-candidate stack.

Until the corresponding feature ships, each scenario skips with a reason naming
the phase that unblocks it — so the plan and the tests stay in lockstep and the
UAT surface is visible from day one.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.uat


def test_uat01_adt_ingest_then_fhir_read() -> None:
    """UAT-01: an ADT message ingested over MLLP is retrievable via FHIR read.

    See docs/UAT_PLAN.md UAT-01. Unblocked when HL7 ingestion (Phase 4-5) and
    the FHIR API (Phase 6-7) are both present.
    """
    pytest.skip("Pending Phase 4-7. Scenario defined in docs/UAT_PLAN.md UAT-01.")


def test_uat02_deidentified_store_has_no_phi() -> None:
    """UAT-02: the de-identified store exposes no Safe Harbor identifiers.

    See docs/UAT_PLAN.md UAT-02. Unblocked when de-identification (Phase 10) ships.
    """
    pytest.skip("Pending Phase 10. Scenario defined in docs/UAT_PLAN.md UAT-02.")
