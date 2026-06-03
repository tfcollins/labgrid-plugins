from app.catalog import BoardCatalog
from app.matching import MatchResult, match_places
from app.models import PlaceModel

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


def _place(name, *, part=None, carrier=None, strategy=None, acquired=None):
    tags = {}
    if part:
        tags["daughter-board"] = part
    if carrier:
        tags["carrier"] = carrier
    if strategy:
        tags["boot-strategy"] = strategy
    return PlaceModel(name=name, tags=tags, acquired=acquired)


def test_unknown_part_is_unsatisfiable():
    res = match_places(CATALOG, [], part="nosuchpart")
    assert isinstance(res, MatchResult)
    assert res.satisfiable is False
    assert "unknown part" in res.reason


def test_unknown_carrier_is_unsatisfiable():
    res = match_places(CATALOG, [], part="adrv9002", carrier="vcu118")
    assert res.satisfiable is False
    assert "carrier" in res.reason


def test_no_live_place_is_unsatisfiable():
    res = match_places(CATALOG, [_place("other", part="ad9081")], part="adrv9002")
    assert res.satisfiable is False
    assert "no live place" in res.reason


def test_match_returns_filter_image_and_strategy():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9002", "carrier": "zcu102"}
    assert res.image == "kuiper-2023_R2"
    assert res.strategy == "BootFPGASoC"
    assert res.place == "p1"


def test_match_without_carrier_omits_carrier_from_filter():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9002"}


def test_match_prefers_a_free_place_for_place_field():
    places = [
        _place("busy", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC", acquired="bob"),
        _place("free", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC"),
    ]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    assert res.place == "free"


def test_bootfile_pin_flows_into_image():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102", bootfile="2023_R2_P1")
    assert res.image == "2023_R2_P1"
