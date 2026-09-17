"""Unit tests for the Prometheus /metrics endpoint and request metering."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from hip.gateway.app import create_app

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    # Metrics/logging are configured in lifespan; TestClient(with) triggers it.
    with TestClient(app) as started:
        yield started


def test_metrics_endpoint_exposes_prometheus_text(client: TestClient) -> None:
    # Generate at least one metered request (health is unmetered, so hit a real route).
    client.get("/fhir/Patient/00000000-0000-0000-0000-000000000000")
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "http_requests_total" in resp.text


def test_metrics_label_uses_route_template_not_ids(client: TestClient) -> None:
    client.get("/fhir/Patient/11111111-1111-1111-1111-111111111111")
    body = client.get("/metrics").text
    # The concrete id must never appear as a label; the template does.
    assert "11111111-1111-1111-1111-111111111111" not in body
    assert "/fhir/Patient/{canonical_id}" in body
