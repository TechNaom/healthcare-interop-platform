"""OpenTelemetry distributed tracing.

Vendor-neutral spans across the two hot paths — HL7 ingestion
(parse → route → map → persist) and the FHIR gateway request cycle — so a single
message or request can be followed end to end (SRS 7.3). Spans are exported over
OTLP/HTTP to a collector when ``HIP_OTLP_ENDPOINT`` is set; otherwise a provider
is still installed so spans are created (and testable) but not exported.

Span attributes carry control-plane facts only — never patient content (same
rule as logs/metrics): message-control-id (MSH-10), ack code, failure stage,
message type, HTTP method / route *template* / status. No names, MRNs, or bodies.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_state = {"configured": False}


def configure_tracing(*, endpoint: str | None = None, service_name: str = "hip") -> None:
    """Install a TracerProvider (idempotent). Exports over OTLP/HTTP when an
    endpoint is configured (``HIP_OTLP_ENDPOINT`` or the ``endpoint`` arg)."""
    if _state["configured"]:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    ep = endpoint or os.environ.get("HIP_OTLP_ENDPOINT")
    if ep:
        # Imported lazily so the exporter's transport deps load only when used.
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
            OTLPSpanExporter,
        )

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=ep)))
    trace.set_tracer_provider(provider)
    _state["configured"] = True


def get_tracer(name: str = "hip") -> trace.Tracer:
    """A tracer for creating spans. Safe before ``configure_tracing`` (no-op spans)."""
    return trace.get_tracer(name)
