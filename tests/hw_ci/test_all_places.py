from adi_lg_plugins.hw_ci.all_places import (
    BootLeg,
    build_all_places_matrix,
)
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, strategy="BootFPGASoC", runner="hw-x", acquired=None):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy=strategy,
        acquired=acquired,
        extra_tags={"runner": runner} if runner else {},
    )


def test_uri_bootable_place_becomes_a_uri_leg():
    legs, acquired = build_all_places_matrix(
        [_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")]
    )
    assert acquired == []
    assert legs == [
        BootLeg(
            place="mini2",
            part="adrv9002",
            carrier="zcu102",
            runner="hw-mini2",
            boot_strategy="BootFPGASoC",
            mode="uri",
        )
    ]


def test_noos_place_becomes_a_reserve_leg():
    legs, _ = build_all_places_matrix(
        [_place("jtagbox", "adrv9371", "zc706", strategy="BootNoOSJTAG")]
    )
    assert legs[0].mode == "reserve"


def test_acquired_place_is_skipped_and_reported():
    legs, acquired = build_all_places_matrix(
        [_place("busy", "ad9081", "vcu118", acquired="someone")]
    )
    assert legs == []
    assert acquired == ["busy"]


def test_missing_runner_tag_yields_none_runner():
    legs, _ = build_all_places_matrix([_place("x", "adrv9002", "zcu102", runner=None)])
    assert legs[0].runner is None


def test_as_matrix_dict_shape():
    legs, _ = build_all_places_matrix([_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")])
    assert legs[0].as_matrix_dict() == {
        "place": "mini2",
        "part": "adrv9002",
        "carrier": "zcu102",
        "runner": "hw-mini2",
        "boot_strategy": "BootFPGASoC",
        "mode": "uri",
    }
