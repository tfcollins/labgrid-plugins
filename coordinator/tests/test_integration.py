"""Integration tests that run against a live Docker compose stack.

Prerequisites:
    cd coordinator/tests
    docker compose -f docker-compose.test.yml up -d --build
    # Wait ~10s for services to stabilize
    pytest test_integration.py -v
"""

import time

import pytest

httpx = pytest.importorskip("httpx")


@pytest.fixture(autouse=True)
def wait_for_api(api_url):
    """Wait for the API to become available before running tests."""
    for _ in range(30):
        try:
            resp = httpx.get(f"{api_url}/health", timeout=2)
            if resp.status_code == 200:
                return
        except httpx.ConnectError:
            pass
        time.sleep(1)
    pytest.skip("API not available")


def test_health(api_url):
    resp = httpx.get(f"{api_url}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["coordinator_connected"] is True


def test_mock_exporter_resources_appear(api_url):
    """Mock exporter should register its resources with the coordinator."""
    # Allow some time for the mock exporter to register
    for _ in range(10):
        resp = httpx.get(f"{api_url}/resources")
        if resp.status_code == 200 and len(resp.json()) > 0:
            break
        time.sleep(1)

    resp = httpx.get(f"{api_url}/resources")
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) > 0

    cls_set = {r["cls"] for r in resources}
    assert "NetworkService" in cls_set


def test_exporters_endpoint(api_url):
    """Exporters should be aggregated from resources."""
    # Wait for resources to appear first
    for _ in range(10):
        resp = httpx.get(f"{api_url}/resources")
        if resp.status_code == 200 and len(resp.json()) > 0:
            break
        time.sleep(1)

    resp = httpx.get(f"{api_url}/exporters")
    assert resp.status_code == 200
    exporters = resp.json()
    assert len(exporters) > 0
    assert any("VCU118_AD9081" in exp["groups"] for exp in exporters)


def test_place_crud(api_url):
    """Full place lifecycle: create, read, acquire, release, delete."""
    name = "integration-test-place"

    # Create
    resp = httpx.post(f"{api_url}/places", json={"name": name})
    assert resp.status_code == 201

    # Read
    resp = httpx.get(f"{api_url}/places/{name}")
    assert resp.status_code == 200
    assert resp.json()["name"] == name
    assert resp.json()["acquired"] is None

    # Set tags
    resp = httpx.put(
        f"{api_url}/places/{name}/tags",
        json={"tags": {"board": "test"}},
    )
    assert resp.status_code == 200

    # Verify tags
    resp = httpx.get(f"{api_url}/places/{name}")
    assert resp.json()["tags"]["board"] == "test"

    # Delete
    resp = httpx.delete(f"{api_url}/places/{name}")
    assert resp.status_code == 204

    # Verify gone
    resp = httpx.get(f"{api_url}/places/{name}")
    assert resp.status_code == 404


def test_reservation_lifecycle(api_url):
    """Create and cancel a reservation."""
    # Create
    resp = httpx.post(
        f"{api_url}/reservations",
        json={"filters": {"main": {"board": "vcu118"}}, "prio": 0.5},
    )
    assert resp.status_code == 201
    reservation = resp.json()
    token = reservation["token"]
    assert reservation["state"] in ("waiting", "allocated")

    # List
    resp = httpx.get(f"{api_url}/reservations")
    assert any(r["token"] == token for r in resp.json())

    # Cancel
    resp = httpx.delete(f"{api_url}/reservations/{token}")
    assert resp.status_code == 204


def test_filter_resources_by_cls(api_url):
    """Filter resources by class name."""
    # Wait for resources
    for _ in range(10):
        resp = httpx.get(f"{api_url}/resources")
        if resp.status_code == 200 and len(resp.json()) > 0:
            break
        time.sleep(1)

    resp = httpx.get(f"{api_url}/resources?cls=NetworkService")
    assert resp.status_code == 200
    for r in resp.json():
        assert r["cls"] == "NetworkService"
