def test_unauthenticated_acquire_blocked(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.post("/api/places/vcu118-lab1/acquire")
    assert r.status_code == 401


def test_unauthenticated_release_blocked(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.post("/api/places/vcu118-lab1/release")
    assert r.status_code == 401


def test_unauthenticated_create_place_blocked(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.post("/api/places", json={"name": "x"})
    assert r.status_code == 401


def test_unauthenticated_delete_place_blocked(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.delete("/api/places/vcu118-lab1")
    assert r.status_code == 401


def test_unauthenticated_create_reservation_blocked(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.post("/api/reservations", json={"filters": {"main": {"name": "x"}}})
    assert r.status_code == 401


def test_unauthenticated_list_places_allowed(authed_lifespan_client):
    c = authed_lifespan_client
    r = c.get("/api/places")
    assert r.status_code == 200


def test_authed_acquire_succeeds(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    r = c.post("/api/places/vcu118-lab1/acquire")
    assert r.status_code == 200
