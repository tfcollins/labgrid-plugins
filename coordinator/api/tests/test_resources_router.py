def test_list_resources_empty(client):
    resp = client.get("/api/resources")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_resources_with_data(client_with_data):
    resp = client_with_data.get("/api/resources")
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) == 3


def test_filter_by_exporter(client_with_data):
    resp = client_with_data.get("/api/resources?exporter=lab1-host")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_filter_by_cls(client_with_data):
    resp = client_with_data.get("/api/resources?cls=NetworkService")
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) == 2
    assert all(r["cls"] == "NetworkService" for r in resources)


def test_filter_by_avail(client_with_data):
    resp = client_with_data.get("/api/resources?avail=true")
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) == 2
    assert all(r["avail"] is True for r in resources)


def test_filter_by_avail_false(client_with_data):
    resp = client_with_data.get("/api/resources?avail=false")
    assert resp.status_code == 200
    resources = resp.json()
    assert len(resources) == 1
    assert resources[0]["cls"] == "NetworkService"
    assert resources[0]["group"] == "RPI_CM4"


def test_list_exporters(client_with_data):
    resp = client_with_data.get("/api/exporters")
    assert resp.status_code == 200
    exporters = resp.json()
    assert len(exporters) == 1
    assert exporters[0]["name"] == "lab1-host"
    assert "VCU118_AD9081" in exporters[0]["groups"]
    assert "RPI_CM4" in exporters[0]["groups"]


def test_list_exporters_empty(client):
    resp = client.get("/api/exporters")
    assert resp.status_code == 200
    assert resp.json() == []
