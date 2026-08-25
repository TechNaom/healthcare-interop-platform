"""Gateway health-endpoint tests — the app boots and the probes answer.

In-process via Starlette's TestClient (httpx under the hood), so no containers
needed. Locks the liveness/readiness contract that orchestration depends on.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from hip import __version__
from hip.gateway.app import create_app

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_readyz_ready(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_openapi_served(client: TestClient) -> None:
    """FastAPI exposes the OpenAPI schema — useful for client SDK generation."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"].startswith("Healthcare Interoperability Platform")
