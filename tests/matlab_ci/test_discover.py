"""Tests for adi_lg_plugins.matlab_ci.discover."""

from __future__ import annotations

from adi_lg_plugins.hw_ci.schema import Place
from adi_lg_plugins.matlab_ci.board_map import BoardMap, BoardMapEntry
from adi_lg_plugins.matlab_ci.discover import discover


def _place(name, daughter, carrier="zcu102", acquired=None, hdl_config=None):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
        hdl_config=hdl_config,
        acquired=acquired,
    )


def _map(*entries):
    return BoardMap(entries=tuple(entries))


def test_empty_places():
    bm = _map(BoardMapEntry(matlab_board="x", daughter_board="ad9361"))
    assert discover(bm, []) == []


def test_place_in_map_emits_entry():
    bm = _map(
        BoardMapEntry(
            matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
            daughter_board="adrv9002",
            carrier="zcu102",
        )
    )
    entries = discover(bm, [_place("mini2", "adrv9002")])
    assert len(entries) == 1
    e = entries[0]
    assert e.place == "mini2"
    assert e.matlab_board == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert e.carrier == "zcu102"
    assert e.daughter_board == "adrv9002"
    assert e.boot_strategy == "BootFPGASoC"
    assert e.runner_label == "hw-mini2"


def test_place_not_in_map_is_skipped():
    bm = _map(BoardMapEntry(matlab_board="x", daughter_board="ad9361"))
    # adrv9009 has no board-map row -> no MATLAB test entry point -> skip
    assert discover(bm, [_place("mini2", "adrv9009")]) == []


def test_acquired_place_skipped_by_default():
    bm = _map(BoardMapEntry(matlab_board="x", daughter_board="ad9361"))
    places = [_place("busy", "ad9361", acquired="someuser/host")]
    assert discover(bm, places) == []
    assert len(discover(bm, places, skip_acquired=False)) == 1


def test_entries_sorted_deterministically():
    bm = _map(
        BoardMapEntry(matlab_board="a", daughter_board="ad9361"),
        BoardMapEntry(matlab_board="b", daughter_board="adrv9009"),
    )
    places = [
        _place("zed", "adrv9009"),
        _place("apollo", "ad9361"),
    ]
    entries = discover(bm, places)
    # sorted by (matlab_board, place)
    assert [e.place for e in entries] == ["apollo", "zed"]


def test_as_matrix_dict_shape():
    bm = _map(
        BoardMapEntry(
            matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
            daughter_board="adrv9002",
            carrier="zcu102",
        )
    )
    [e] = discover(bm, [_place("mini2", "adrv9002", hdl_config="m8_l4")])
    d = e.as_matrix_dict()
    assert d == {
        "place": "mini2",
        "matlab_board": "zynqmp-zcu102-rev10-adrv9002-vcmos",
        "carrier": "zcu102",
        "daughter_board": "adrv9002",
        "boot_strategy": "BootFPGASoC",
        "hdl_config": "m8_l4",
        "runner_label": "hw-mini2",
    }
