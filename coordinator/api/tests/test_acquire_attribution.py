def test_acquire_records_logged_in_user_as_owner(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    r = c.post("/api/places/vcu118-lab1/acquire")
    assert r.status_code == 200
    r = c.get("/api/places/vcu118-lab1")
    assert r.json()["acquired_username"] == "alice"


def test_other_user_cannot_release(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    c.post("/api/places/vcu118-lab1/acquire")
    c.post("/api/auth/logout")
    c.login("bob")
    r = c.post("/api/places/vcu118-lab1/release")
    assert r.status_code == 403


def test_owner_can_release(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    c.post("/api/places/vcu118-lab1/acquire")
    r = c.post("/api/places/vcu118-lab1/release")
    assert r.status_code == 200
    r = c.get("/api/places/vcu118-lab1")
    assert r.json()["acquired_username"] is None


def test_admin_can_force_release(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    c.post("/api/places/vcu118-lab1/acquire")
    c.post("/api/auth/logout")
    c.login("rooty", role="admin")
    r = c.post("/api/places/vcu118-lab1/release?force=true")
    assert r.status_code == 200


def test_acquire_already_held_returns_409(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    c.post("/api/places/vcu118-lab1/acquire")
    c.post("/api/auth/logout")
    c.login("bob")
    r = c.post("/api/places/vcu118-lab1/acquire")
    assert r.status_code == 409
