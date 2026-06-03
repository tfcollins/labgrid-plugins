import pytest
from fastapi.testclient import TestClient

from app.catalog import BoardCatalog
from app.main import app
from app.models import PlaceModel

from .conftest import MockCoordinatorClient

CATALOG = BoardCatalog.model_validate(
    {
        "boards": {
            "adrv9002": {
                "image": "kuiper-2023_R2",
                "carriers": {"zcu102": {}},
            }
        }
    }
)


@pytest.fixture
def catalog_client():
    """TestClient with a mock coordinator and a loaded catalog on app.state."""
    coord = MockCoordinatorClient()
    coord._places["adrv9002-zcu102"] = PlaceModel(
        name="adrv9002-zcu102",
        tags={
            "daughter-board": "adrv9002",
            "carrier": "zcu102",
            "boot-strategy": "BootFPGASoC",
        },
    )
    app.state.coordinator = coord
    app.state.catalog = CATALOG
    return TestClient(app)


def test_get_catalog_returns_boards(catalog_client):
    resp = catalog_client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["boards"]["adrv9002"]["image"] == "kuiper-2023_R2"
    assert "zcu102" in data["boards"]["adrv9002"]["carriers"]


def test_match_satisfiable(catalog_client):
    resp = catalog_client.get("/api/match", params={"part": "adrv9002", "carrier": "zcu102"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["satisfiable"] is True
    assert data["reservation_filter"] == {"daughter-board": "adrv9002", "carrier": "zcu102"}
    assert data["image"] == "kuiper-2023_R2"
    assert data["strategy"] == "BootFPGASoC"
    assert data["place"] == "adrv9002-zcu102"


def test_match_unknown_part_is_satisfiable_false(catalog_client):
    resp = catalog_client.get("/api/match", params={"part": "nosuchpart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["satisfiable"] is False
    assert "unknown part" in data["reason"]


def test_match_requires_part(catalog_client):
    resp = catalog_client.get("/api/match")
    assert resp.status_code == 422  # FastAPI: missing required query param


def test_match_invalid_carrier_is_satisfiable_false(catalog_client):
    resp = catalog_client.get("/api/match", params={"part": "adrv9002", "carrier": "vcu118"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["satisfiable"] is False
    assert "carrier" in data["reason"]


def test_match_bootfile_pin_flows_through_http(catalog_client):
    resp = catalog_client.get(
        "/api/match",
        params={"part": "adrv9002", "carrier": "zcu102", "bootfile": "2023_R2_P1"},
    )
    assert resp.status_code == 200
    assert resp.json()["image"] == "2023_R2_P1"
