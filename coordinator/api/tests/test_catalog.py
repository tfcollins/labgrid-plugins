import textwrap

import pytest

from app.catalog import (
    Catalog,
    MatchData,
    ResolvedBoard,
    UnknownPart,
    UnresolvableVersion,
    load_catalog,
    match_places,
    resolve_board,
)

CATALOG_YAML = textwrap.dedent(
    """
    channels:
      kuiper-stable: "2023_R2_P1"
    boards:
      ad9361:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3}
          zc706:  {matlab_board: zynq-zc706-adv7511-ad9361-fmcomms2-3}
      ad9081:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9081}
    """
)


@pytest.fixture
def catalog(tmp_path):
    p = tmp_path / "board_catalog.yaml"
    p.write_text(CATALOG_YAML)
    return load_catalog(p)


def test_load_catalog_parses_channels_and_boards(catalog):
    assert isinstance(catalog, Catalog)
    assert catalog.channels["kuiper-stable"] == "2023_R2_P1"
    assert set(catalog.boards) == {"ad9361", "ad9081"}
    assert catalog.boards["ad9361"].carriers["zcu102"].matlab_board.endswith("fmcomms2-3")


def test_resolve_board_defaults_to_channel_latest(catalog):
    r = resolve_board(catalog, part="ad9361")
    assert isinstance(r, ResolvedBoard)
    assert r.part == "ad9361"
    assert r.version == "2023_R2_P1"
    assert r.matlab_boards == {
        "zcu102": "zynqmp-zcu102-rev10-ad9361-fmcomms2-3",
        "zc706": "zynq-zc706-adv7511-ad9361-fmcomms2-3",
    }


def test_resolve_board_honours_pinned_bootfile(catalog):
    r = resolve_board(catalog, part="ad9361", bootfile="2024_R1")
    assert r.version == "2024_R1"


def test_resolve_board_unknown_part_raises(catalog):
    with pytest.raises(UnknownPart):
        resolve_board(catalog, part="nope")


def test_resolve_board_raises_when_channel_unresolvable(catalog):
    bad_catalog = Catalog(channels={}, boards=catalog.boards)
    with pytest.raises(UnresolvableVersion):
        resolve_board(bad_catalog, part="ad9081")


def _place(name, daughter, carrier, *, acquired=None, strategy="BootFPGASoC"):
    return {
        "name": name,
        "acquired": acquired,
        "tags": {
            "daughter-board": daughter,
            "carrier": carrier,
            "boot-strategy": strategy,
        },
    }


def test_match_places_filters_by_part(catalog):
    places = [
        _place("p1", "ad9361", "zcu102"),
        _place("p2", "ad9081", "zcu102"),
    ]
    m = match_places(catalog, places, part="ad9361")
    assert isinstance(m, MatchData)
    assert m.satisfiable is True
    assert m.reservation_filter == {"daughter-board": "ad9361"}
    assert [c.place for c in m.candidates] == ["p1"]
    assert m.version == "2023_R2_P1"


def test_match_places_narrows_by_carrier(catalog):
    places = [
        _place("p1", "ad9361", "zcu102"),
        _place("p3", "ad9361", "zc706"),
    ]
    m = match_places(catalog, places, part="ad9361", carrier="zc706")
    assert m.reservation_filter == {"daughter-board": "ad9361", "carrier": "zc706"}
    assert [c.place for c in m.candidates] == ["p3"]


def test_match_places_no_live_place_is_unsatisfiable(catalog):
    m = match_places(catalog, [], part="ad9361")
    assert m.satisfiable is False
    assert "no matching" in m.reason.lower()


def test_match_places_unknown_part_is_unsatisfiable(catalog):
    m = match_places(catalog, [_place("p1", "ad9361", "zcu102")], part="nope")
    assert m.satisfiable is False
    assert "catalog" in m.reason.lower()
