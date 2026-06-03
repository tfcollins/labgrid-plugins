import textwrap
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

CATALOG_YAML = textwrap.dedent(
    """
    channels:
      kuiper-stable: "2023_R2_P1"
    boards:
      ad9361:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3}
    """
)


class FakeCoordinator:
    def __init__(self, places):
        self._places = places

    def get_places(self):
        return self._places


def _place(name, daughter, carrier, *, acquired=None):
    return {
        "name": name,
        "acquired": acquired,
        "tags": {"daughter-board": daughter, "carrier": carrier, "boot-strategy": "BootFPGASoC"},
    }


@pytest.fixture
def client(tmp_path):
    from app.config import settings as cfg
    from app.main import app

    catalog_file = tmp_path / "board_catalog.yaml"
    catalog_file.write_text(CATALOG_YAML)
    cfg.board_catalog_path = str(catalog_file)

    fake = FakeCoordinator([_place("p1", "ad9361", "zcu102"), _place("p2", "ad9081", "zcu102")])

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.coordinator = fake
        yield

    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:
        yield c


def test_get_catalog(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert r.json()["channels"]["kuiper-stable"] == "2023_R2_P1"


def test_match_satisfiable(client):
    r = client.get("/api/match", params={"part": "ad9361"})
    assert r.status_code == 200
    body = r.json()
    assert body["satisfiable"] is True
    assert body["reservation_filter"] == {"daughter-board": "ad9361"}
    assert body["version"] == "2023_R2_P1"
    assert [c["place"] for c in body["candidates"]] == ["p1"]


def test_match_no_place(client):
    r = client.get("/api/match", params={"part": "ad9361", "carrier": "zc706"})
    assert r.status_code == 200
    assert r.json()["satisfiable"] is False
