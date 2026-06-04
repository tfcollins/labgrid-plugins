from __future__ import annotations

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


# The zc706 daughter-boards (nemo=adrv9009, bq=adrv9371) boot via JTAG
# recovery rather than the adrv9002 SD-mux/Kuiper path. Matching is generic,
# but lock the part->place/strategy resolution so a regression in either the
# 1:1 part==daughter-board contract or the boot-strategy passthrough is caught.
JTAG_CATALOG = BoardCatalog.model_validate(
    {
        "boards": {
            "adrv9009": {"image": "2023_R2_P1", "carriers": {"zc706": {}}},
            "adrv9371": {"image": "2023_R2_P1", "carriers": {"zc706": {}}},
        }
    }
)


def test_match_adrv9009_resolves_jtag_recovery_place():
    places = [_place("nemo", part="adrv9009", carrier="zc706", strategy="BootZynq7000JTAGRecovery")]
    res = match_places(JTAG_CATALOG, places, part="adrv9009", carrier="zc706")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9009", "carrier": "zc706"}
    assert res.image == "2023_R2_P1"
    assert res.strategy == "BootZynq7000JTAGRecovery"
    assert res.place == "nemo"


def test_match_adrv9371_resolves_jtag_recovery_place():
    # adrv9371 == the AD9371 eval board (pyadi adi.ad9371); the place tag and
    # the pyadi HW smoke marker are both "adrv9371", so that is the part key.
    places = [_place("bq", part="adrv9371", carrier="zc706", strategy="BootZynq7000JTAGRecovery")]
    res = match_places(JTAG_CATALOG, places, part="adrv9371", carrier="zc706")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9371", "carrier": "zc706"}
    assert res.strategy == "BootZynq7000JTAGRecovery"
    assert res.place == "bq"


# An alias lets a chip name (ad9371) resolve to its eval board (adrv9371). The
# reservation filter must use the CANONICAL daughter-board so it matches the
# place tag, never the alias the caller happened to type.
ALIAS_CATALOG = BoardCatalog.model_validate(
    {
        "boards": {
            "adrv9371": {
                "aliases": ["ad9371"],
                "image": "2023_R2_P1",
                "carriers": {"zc706": {}},
            }
        }
    }
)


def test_match_alias_resolves_to_canonical_board():
    places = [_place("bq", part="adrv9371", carrier="zc706", strategy="BootZynq7000JTAGRecovery")]
    res = match_places(ALIAS_CATALOG, places, part="ad9371", carrier="zc706")
    assert res.satisfiable is True
    # filter targets the real place tag (adrv9371), not the requested alias.
    assert res.reservation_filter == {"daughter-board": "adrv9371", "carrier": "zc706"}
    assert res.strategy == "BootZynq7000JTAGRecovery"
    assert res.place == "bq"


# daq3 on vcu118 (nuc) boots by loading the FPGA fabric via JTAG (BootFabric);
# it has no downloadable Kuiper image, so image resolves to None.
FABRIC_CATALOG = BoardCatalog.model_validate({"boards": {"daq3": {"carriers": {"vcu118": {}}}}})


def test_match_daq3_resolves_bootfabric_place_with_no_image():
    places = [_place("nuc", part="daq3", carrier="vcu118", strategy="BootFabric")]
    res = match_places(FABRIC_CATALOG, places, part="daq3", carrier="vcu118")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "daq3", "carrier": "vcu118"}
    assert res.strategy == "BootFabric"
    assert res.image is None
    assert res.place == "nuc"


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


def test_carrier_filter_excludes_wrong_carrier_places():
    # zcu102 and vcu118 are both valid catalog carriers; only a vcu118 place
    # is live, but we request zcu102 -> the carrier filter excludes it.
    catalog = BoardCatalog.model_validate(
        {
            "boards": {
                "adrv9002": {
                    "image": "kuiper-2023_R2",
                    "carriers": {"zcu102": {}, "vcu118": {}},
                }
            }
        }
    )
    places = [_place("p1", part="adrv9002", carrier="vcu118")]
    res = match_places(catalog, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is False
    assert "no live place" in res.reason


def test_missing_boot_strategy_tag_yields_strategy_none():
    places = [_place("p1", part="adrv9002", carrier="zcu102")]  # no strategy kwarg
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    assert res.strategy is None


def test_unknown_boot_strategy_tag_yields_strategy_none():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootTypoFoo")]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    assert res.strategy is None
