"""OpenTelemetry metrics with a Prometheus exposition endpoint.

Vendor-neutral metrics (SRS 7.3, docs/TECH_STACK.md): an OTel meter feeds a
Prometheus reader that a scraper reads from ``GET /metrics``. Two instruments
cover request-level ops visibility — a request counter (by method + status) and a
latency histogram. As with logs, metric labels carry no PHI: the path is the
route *template* (``/fhir/Patient/{canonical_id}``), never the concrete id.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

_state = {"configured": False}


def configure_metrics() -> None:
    """Install a MeterProvider backed by the Prometheus reader (idempotent)."""
    if _state["configured"]:
        return
    metrics.set_meter_provider(MeterProvider(metric_readers=[PrometheusMetricReader()]))
    _state["configured"] = True


def _meter() -> metrics.Meter:
    return metrics.get_meter("hip.gateway")


class RequestMetrics:
    """Request counter + latency histogram, recorded by the gateway middleware."""

    def __init__(self) -> None:
        meter = _meter()
        self._count = meter.create_counter(
            "http_requests_total", description="HTTP requests handled by the gateway"
        )
        self._latency = meter.create_histogram(
            "http_request_duration_seconds", unit="s", description="Request latency"
        )

    def record(self, *, method: str, route: str, status: int, duration_s: float) -> None:
        attrs = {"method": method, "route": route, "status": str(status)}
        self._count.add(1, attrs)
        self._latency.record(duration_s, attrs)


def render_latest() -> tuple[bytes, str]:
    """Prometheus exposition payload + content type for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
