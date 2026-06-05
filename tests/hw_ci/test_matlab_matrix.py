from adi_lg_plugins.hw_ci.board_map import (
    BoardMap,
    BoardMapEntry,
    MatlabLeg,
    build_matlab_matrix,
)
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, hdl=None, runner="hw-x", acquired=None):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
        hdl_config=hdl,
        acquired=acquired,
        extra_tags={"runner": runner},
    )


_BM = BoardMap(
    entries=(
        BoardMapEntry(
            matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
            daughter_board="adrv9002",
            carrier="zcu102",
        ),
    )
)


def test_build_emits_one_leg_per_mapped_live_place():
    places = [_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")]
    legs, skipped = build_matlab_matrix(places, _BM)
    assert skipped == []
    assert legs == [
        MatlabLeg(
            part="adrv9002",
            carrier="zcu102",
            runner="hw-mini2",
            matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
        )
    ]


def test_build_skips_unmapped_live_place():
    places = [_place("nuc", "daq3", "vcu118", runner="hw-nuc")]
    legs, skipped = build_matlab_matrix(places, _BM)
    assert legs == []
    assert skipped == ["nuc"]


def test_build_skips_acquired_place():
    places = [_place("mini2", "adrv9002", "zcu102", acquired="someone")]
    legs, skipped = build_matlab_matrix(places, _BM)
    assert legs == []
    assert skipped == []


def test_build_runner_defaults_to_none_when_no_runner_tag():
    p = Place(
        name="x",
        carrier="zcu102",
        daughter_board="adrv9002",
        boot_strategy="BootFPGASoC",
        extra_tags={},
    )
    legs, _ = build_matlab_matrix([p], _BM)
    assert legs[0].runner is None
