"""Compliance: no PHI in logs (HIPAA, docs/TEST_STRATEGY.md 4, SRS 7.3).

Run PHI-laden messages through the pipeline while capturing every structured log
event, then assert none of the known synthetic patient values appear. Because
fixtures are synthetic, their exact values are known — that is what makes this
test possible.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from structlog.testing import capture_logs

from hip.messaging.hl7.listener import ingest
from hip.observability.logging import configure_logging, get_logger

pytestmark = [pytest.mark.unit, pytest.mark.compliance]

# Synthetic PHI values that must never appear in any log line.
_PHI_TOKENS = ("DOE", "JANE", "MRN12345", "19800101", "555")

_PHI_ADT = (
    "MSH|^~\\&|SENDAPP|SENDFAC|R|RF|20260825101500||ADT^A01|MSG1|P|2.5\r"
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE||19800101|F|||123 MAIN ST^^METRO^NY^10001|||555-1212\r"
    "PV1|1|I|WARD^101^A\r"
)

_PHI_ORU_BAD = (
    "MSH|^~\\&|LAB|LF|R|RF|20260825101500||ORU^R01|MSG2|P|2.5\r"
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE||19800101|F\r"
    "OBX|1|ZZ|1^x^L||DOE-secret-value||||||F\r"  # unmapped type -> transform failure
)


def _run_and_capture(raw: str) -> list[MutableMapping[str, Any]]:
    with capture_logs() as logs:
        # Map-only (no session) still logs the outcome with non-PHI fields.
        asyncio.run(ingest(raw))
    return logs


@pytest.mark.parametrize("raw", [_PHI_ADT, _PHI_ORU_BAD])
def test_pipeline_logs_contain_no_phi(raw: str) -> None:
    logs = _run_and_capture(raw)
    blob = json.dumps(logs)
    for token in _PHI_TOKENS:
        assert token not in blob, f"PHI token {token!r} leaked into logs: {blob}"


def test_outcome_is_logged_with_safe_fields() -> None:
    logs = _run_and_capture(_PHI_ADT)
    outcome = next(e for e in logs if e.get("event") == "message_ingested")
    assert outcome["ack"] == "AA"
    assert outcome["control_id"] == "MSG1"  # MSH-10 message id is not PHI
    assert outcome["source"] == "SENDAPP/SENDFAC"  # sending system is not PHI


def test_configure_logging_runs() -> None:
    configure_logging(json_logs=True)
    assert get_logger("test") is not None
