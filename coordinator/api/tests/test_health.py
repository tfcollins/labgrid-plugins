def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["coordinator_connected"] is True
    assert data["coordinator_address"] == "mock:20408"
