def test_list_reservations_empty(client):
    resp = client.get("/api/reservations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_reservation(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.post(
        "/api/reservations",
        json={
            "filters": {"main": {"board": "vcu118"}},
            "prio": 1.0,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["owner"] == "test-user"
    assert data["token"] == "ABCDEF1234"
    assert data["state"] == "waiting"
    assert data["prio"] == 1.0


def test_create_and_list_reservations(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    c.post(
        "/api/reservations",
        json={"filters": {"main": {"board": "vcu118"}}},
    )
    resp = c.get("/api/reservations")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_cancel_reservation(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    c.post(
        "/api/reservations",
        json={"filters": {"main": {"board": "vcu118"}}},
    )
    resp = c.delete("/api/reservations/ABCDEF1234")
    assert resp.status_code == 204

    resp = c.get("/api/reservations")
    assert len(resp.json()) == 0


def test_poll_reservation(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    c.post(
        "/api/reservations",
        json={"filters": {"main": {"board": "vcu118"}}},
    )
    resp = c.post("/api/reservations/ABCDEF1234/poll")
    assert resp.status_code == 200
    assert resp.json()["token"] == "ABCDEF1234"
