"""Performance tier — asserts SRS 7.1 targets in CI's scheduled perf job.

These are marked ``performance`` and are excluded from the default (per-PR) run;
they execute in the scheduled workflow (.github/workflows/performance.yml) once
there is a running stack to drive. Until the gateway exists (Phase 1+), they
skip with a clear reason rather than fail, so the tier is wired end-to-end from
day one.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.performance

# The perf job sets HIP_PERF_TARGET to the base URL of a running stack.
PERF_TARGET = os.environ.get("HIP_PERF_TARGET")


@pytest.mark.skipif(
    PERF_TARGET is None,
    reason="No running stack (set HIP_PERF_TARGET). Gateway endpoints arrive in Phase 1+.",
)
def test_fhir_read_p95_under_300ms() -> None:
    """P95 latency for a FHIR read stays under the SRS 7.1 target.

    Implemented once the FHIR API exists (Phase 6-7): drive N reads against the
    generated Synthea population and assert the P95 budget. Placeholder now so
    the target is documented and the tier runs.
    """
    pytest.skip("Pending FHIR API (Phase 6-7); target: P95 < 300ms per SRS 7.1.")
