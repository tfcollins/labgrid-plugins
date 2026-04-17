"""Integration tests for GET /api/places/{name}/env-yaml."""

import yaml


def test_env_yaml_shell_tier(client_with_data):
    r = client_with_data.get("/api/places/vcu118-lab1/env-yaml?tier=shell")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/x-yaml; charset=utf-8"
    assert "attachment" in r.headers.get("content-disposition", "")
    doc = yaml.safe_load(r.text)
    assert doc["targets"]["main"]["resources"]["RemotePlace"]["name"] == "vcu118-lab1"
    assert "SerialDriver" in doc["targets"]["main"]["drivers"]
    assert "ADIShellDriver" in doc["targets"]["main"]["drivers"]


def test_env_yaml_drivers_tier(client_with_data):
    r = client_with_data.get("/api/places/vcu118-lab1/env-yaml?tier=drivers")
    assert r.status_code == 200
    doc = yaml.safe_load(r.text)
    assert "SerialDriver" in doc["targets"]["main"]["drivers"]


def test_env_yaml_boot_tier(client_with_data):
    r = client_with_data.get("/api/places/vcu118-lab1/env-yaml?tier=boot")
    assert r.status_code == 200


def test_env_yaml_default_tier_is_shell(client_with_data):
    r = client_with_data.get("/api/places/vcu118-lab1/env-yaml")
    assert r.status_code == 200
    doc = yaml.safe_load(r.text)
    drivers = doc["targets"]["main"]["drivers"]
    assert len(drivers) == 2  # SerialDriver + ADIShellDriver only


def test_env_yaml_404_for_unknown_place(client_with_data):
    r = client_with_data.get("/api/places/nonexistent/env-yaml?tier=shell")
    assert r.status_code == 404


def test_env_yaml_422_for_invalid_tier(client_with_data):
    r = client_with_data.get("/api/places/vcu118-lab1/env-yaml?tier=bogus")
    assert r.status_code == 422
