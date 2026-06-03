import textwrap

import pytest

from app.catalog import (
    Catalog,
    ResolvedBoard,
    UnknownPart,
    UnresolvableVersion,  # noqa: F401
    load_catalog,
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
