import pytest

from adi_lg_plugins.hw_ci.board_map import (
    BoardMap,
    BoardMapEntry,
    BoardMapError,
    load_board_map,
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


def test_lookup_returns_matlab_board_for_matching_place():
    bm = BoardMap(
        entries=(
            BoardMapEntry(
                matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
                daughter_board="adrv9002",
                carrier="zcu102",
            ),
        )
    )
    assert bm.lookup(_place("mini2", "adrv9002", "zcu102")) == "zynqmp-zcu102-rev10-adrv9002-vcmos"


def test_lookup_no_match_returns_none():
    bm = BoardMap(entries=(BoardMapEntry(matlab_board="x", daughter_board="adrv9009"),))
    assert bm.lookup(_place("mini2", "adrv9002", "zcu102")) is None


def test_lookup_most_specific_entry_wins():
    bm = BoardMap(
        entries=(
            BoardMapEntry(matlab_board="generic", daughter_board="adrv9002"),
            BoardMapEntry(
                matlab_board="lvds", daughter_board="adrv9002", carrier="zcu102", hdl_config="lvds"
            ),
        )
    )
    assert bm.lookup(_place("m", "adrv9002", "zcu102", hdl="lvds")) == "lvds"
    assert bm.lookup(_place("m", "adrv9002", "zed")) == "generic"


def test_load_board_map_parses_boards_list(tmp_path):
    p = tmp_path / "board_map.yaml"
    p.write_text(
        "boards:\n"
        "  - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}\n"
        "  - {daughter-board: pluto, matlab_board: pluto}\n"
    )
    bm = load_board_map(str(p))
    assert len(bm.entries) == 2
    assert bm.entries[0].carrier == "zcu102"
    assert bm.entries[1].carrier is None


def test_load_board_map_rejects_entry_missing_required_keys(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("boards:\n  - {carrier: zcu102, matlab_board: foo}\n")
    with pytest.raises(BoardMapError):
        load_board_map(str(p))


def test_load_board_map_rejects_missing_boards_key(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("not_boards: []\n")
    with pytest.raises(BoardMapError):
        load_board_map(str(p))
