"""Tests for adi_lg_plugins.matlab_ci.board_map."""

from __future__ import annotations

import textwrap

import pytest

from adi_lg_plugins.hw_ci.schema import Place
from adi_lg_plugins.matlab_ci.board_map import (
    BoardMap,
    BoardMapError,
    load_board_map,
)


def _place(daughter, carrier="zcu102", hdl_config=None, strat="BootFPGASoC"):
    return Place(
        name="p",
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy=strat,
        hdl_config=hdl_config,
    )


def _write(tmp_path, text):
    f = tmp_path / "board_map.yaml"
    f.write_text(textwrap.dedent(text), encoding="utf-8")
    return f


def test_load_parses_entries(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
          - {daughter-board: ad9361, matlab_board: zynq-zed-adv7511-ad9361-fmcomms2-3}
        """,
    )
    bm = load_board_map(f)
    assert isinstance(bm, BoardMap)
    assert len(bm.entries) == 2


def test_lookup_by_daughter_board_only(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {daughter-board: ad9361, matlab_board: zynq-zed-adv7511-ad9361-fmcomms2-3}
        """,
    )
    bm = load_board_map(f)
    # carrier-agnostic entry matches regardless of carrier
    assert bm.lookup(_place("ad9361", carrier="zc706")) == "zynq-zed-adv7511-ad9361-fmcomms2-3"


def test_lookup_prefers_carrier_specific_entry(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {daughter-board: adrv9002, matlab_board: generic-adrv9002}
          - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
        """,
    )
    bm = load_board_map(f)
    # the carrier-specific entry wins for zcu102
    assert bm.lookup(_place("adrv9002", carrier="zcu102")) == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    # falls back to the generic entry on a different carrier
    assert bm.lookup(_place("adrv9002", carrier="zc706")) == "generic-adrv9002"


def test_lookup_narrows_on_hdl_config(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {carrier: zcu102, daughter-board: ad9081, matlab_board: ad9081-default}
          - {carrier: zcu102, daughter-board: ad9081, hdl-config: m8_l4, matlab_board: ad9081-m8l4}
        """,
    )
    bm = load_board_map(f)
    assert bm.lookup(_place("ad9081", hdl_config="m8_l4")) == "ad9081-m8l4"
    assert bm.lookup(_place("ad9081", hdl_config="m4_l2")) == "ad9081-default"


def test_lookup_returns_none_when_no_match(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {daughter-board: ad9361, matlab_board: x}
        """,
    )
    bm = load_board_map(f)
    assert bm.lookup(_place("adrv9009")) is None


def test_missing_file_raises(tmp_path):
    with pytest.raises(BoardMapError):
        load_board_map(tmp_path / "does-not-exist.yaml")


def test_entry_missing_required_keys_raises(tmp_path):
    f = _write(
        tmp_path,
        """
        boards:
          - {carrier: zcu102, matlab_board: oops-no-daughter}
        """,
    )
    with pytest.raises(BoardMapError):
        load_board_map(f)


def test_empty_or_malformed_top_level_raises(tmp_path):
    f = _write(tmp_path, "not_a_boards_key: []\n")
    with pytest.raises(BoardMapError):
        load_board_map(f)
