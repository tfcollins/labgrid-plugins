def test_list_places_empty(client):
    resp = client.get("/api/places")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_places_with_data(client_with_data):
    resp = client_with_data.get("/api/places")
    assert resp.status_code == 200
    places = resp.json()
    assert len(places) == 2
    names = {p["name"] for p in places}
    assert names == {"vcu118-lab1", "rpi-lab1"}


def test_get_place(client_with_data):
    resp = client_with_data.get("/api/places/vcu118-lab1")
    assert resp.status_code == 200
    place = resp.json()
    assert place["name"] == "vcu118-lab1"
    assert place["tags"]["board"] == "vcu118"
    assert len(place["matches"]) == 1


def test_get_place_not_found(client):
    resp = client.get("/api/places/nonexistent")
    assert resp.status_code == 404


def test_create_place(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.post("/api/places", json={"name": "new-place"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "new-place"

    # Verify it exists now
    resp = c.get("/api/places/new-place")
    assert resp.status_code == 200


def test_delete_place(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.delete("/api/places/vcu118-lab1")
    assert resp.status_code == 204

    resp = c.get("/api/places/vcu118-lab1")
    assert resp.status_code == 404


def test_acquire_and_release_place(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.post("/api/places/vcu118-lab1/acquire")
    assert resp.status_code == 200

    resp = c.get("/api/places/vcu118-lab1")
    assert resp.json()["acquired"] == "test-user"

    resp = c.post("/api/places/vcu118-lab1/release")
    assert resp.status_code == 200

    resp = c.get("/api/places/vcu118-lab1")
    assert resp.json()["acquired"] is None


def test_set_tags(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.put(
        "/api/places/vcu118-lab1/tags",
        json={"tags": {"board": "vcu118", "location": "lab2"}},
    )
    assert resp.status_code == 200

    resp = c.get("/api/places/vcu118-lab1")
    assert resp.json()["tags"]["location"] == "lab2"


def test_set_comment(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.put(
        "/api/places/vcu118-lab1/comment",
        json={"comment": "Test board in lab 1"},
    )
    assert resp.status_code == 200

    resp = c.get("/api/places/vcu118-lab1")
    assert resp.json()["comment"] == "Test board in lab 1"


def test_add_match(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("tester")
    resp = c.post(
        "/api/places/vcu118-lab1/matches",
        json={"pattern": "lab1-host/VCU118_AD9081/NetworkService"},
    )
    assert resp.status_code == 200

    resp = c.get("/api/places/vcu118-lab1")
    assert len(resp.json()["matches"]) == 2


def test_set_tags_updates_catalog(authed_lifespan_client, tmp_path, monkeypatch):
    from app.catalog import BoardCatalog
    from app.config import settings

    # Point catalog path to a temp file
    catalog_path = tmp_path / "board_catalog.yaml"
    monkeypatch.setattr(settings, "board_catalog_path", str(catalog_path))

    # Initialize catalog in app state
    catalog = BoardCatalog(boards={})
    authed_lifespan_client.app.state.catalog = catalog

    c = authed_lifespan_client
    c.login("tester")

    # Put tags with a new daughter board and carrier
    resp = c.put(
        "/api/places/vcu118-lab1/tags",
        json={"tags": {"daughter-board": "new-chip", "carrier": "zcu102"}},
    )
    assert resp.status_code == 200

    # Verify catalog is updated in memory
    assert "new-chip" in catalog.boards
    assert "zcu102" in catalog.boards["new-chip"].carriers

    # Verify catalog is saved to file
    assert catalog_path.exists()
    import yaml

    saved = yaml.safe_load(catalog_path.read_text())
    assert "new-chip" in saved["boards"]
    assert "zcu102" in saved["boards"]["new-chip"]["carriers"]
