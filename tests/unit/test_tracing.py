"""Unit tests for OpenTelemetry tracing across the ingest pipeline.

Captures spans with an in-memory exporter and asserts (a) a span is emitted per
ingested message and (b) span attributes carry no PHI (same rule as logs/metrics).
"""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from hip.messaging.hl7.listener import ingest
from hip.observability.tracing import configure_tracing

pytestmark = pytest.mark.unit

# PHI that appears in the message below and must never leak into span attributes.
_PHI = "MRN12345"
_ADT = (
    "MSH|^~\\&|SEND|SF|RECV|RF|20260101120000||ADT^A01|CTRL-9|P|2.5\r"
    "PID|1||MRN12345^^^HOSP^MR||DOE^JANE||19800101|F\r"
    "PV1|1|I|WARD^101^A\r"
)


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    """Install a captured tracer provider (once) and return the in-memory sink."""
    configure_tracing()  # ensure a real SDK provider is installed
    provider = trace.get_tracer_provider()
    exporter = InMemorySpanExporter()
    assert isinstance(provider, TracerProvider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return exporter


def test_ingest_emits_span_with_control_plane_attributes(
    span_exporter: InMemorySpanExporter,
) -> None:
    result = asyncio.run(ingest(_ADT))  # map-only (no session factory)
    assert result.ack_code.value == "AA"

    spans = span_exporter.get_finished_spans()
    ingest_spans = [s for s in spans if s.name == "hl7.ingest"]
    assert ingest_spans, "expected an hl7.ingest span"
    attrs = dict(ingest_spans[-1].attributes or {})
    assert attrs.get("hl7.ack") == "AA"
    assert attrs.get("hl7.message_code") == "ADT"
    assert attrs.get("hl7.control_id") == "CTRL-9"


def test_span_attributes_carry_no_phi(span_exporter: InMemorySpanExporter) -> None:
    asyncio.run(ingest(_ADT))
    for span in span_exporter.get_finished_spans():
        for key, value in (span.attributes or {}).items():
            assert _PHI not in str(value), f"PHI leaked into span attribute {key}"
            assert "DOE" not in str(value), f"PHI (name) leaked into span attribute {key}"
