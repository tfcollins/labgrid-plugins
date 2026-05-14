"""Tests for adi_lg_plugins.hw_ci.intersect.intersect."""

from __future__ import annotations

from adi_lg_plugins.hw_ci.intersect import MarkerSpec, intersect
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier="zcu102", strat="BootFPGASoC", **kw):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy=strat,
        **kw,
    )


def test_empty_inputs():
    assert intersect({}, []) == []
    assert intersect({}, [_place("mini2", "ad9081")]) == []
    assert intersect({"t::a": MarkerSpec.of(["ad9081"])}, []) == []


def test_happy_path_single_test_single_place():
    markers = {"test/hw/test_ad9081.py::test_rx": MarkerSpec.of(["ad9081"])}
    places = [_place("mini2", "ad9081")]
    entries = intersect(markers, places)
    assert len(entries) == 1
    e = entries[0]
    assert e.place == "mini2"
    assert e.carrier == "zcu102"
    assert e.daughter_board == "ad9081"
    assert e.boot_strategy == "BootFPGASoC"
    assert e.marker_filter == "iio_hardware"
    assert e.tests == ("test/hw/test_ad9081.py::test_rx",)


def test_multiple_tests_same_place_grouped():
    markers = {
        "test/hw/test_a.py::test_1": MarkerSpec.of(["ad9081"]),
        "test/hw/test_a.py::test_2": MarkerSpec.of(["ad9081"]),
    }
    places = [_place("mini2", "ad9081")]
    entries = intersect(markers, places)
    assert len(entries) == 1
    # tests are deterministically sorted
    assert entries[0].tests == (
        "test/hw/test_a.py::test_1",
        "test/hw/test_a.py::test_2",
    )


def test_multiple_daughters_one_test_each():
    markers = {
        "a::t": MarkerSpec.of(["ad9081"]),
        "b::t": MarkerSpec.of(["adrv9009"]),
    }
    places = [
        _place("mini2", "ad9081"),
        _place("nemo", "adrv9009", carrier="zc706"),
    ]
    entries = intersect(markers, places)
    daughters = {e.daughter_board for e in entries}
    assert daughters == {"ad9081", "adrv9009"}
    # Entries are sorted by (daughter, place)
    assert entries[0].daughter_board == "ad9081"
    assert entries[1].daughter_board == "adrv9009"


def test_carrier_narrowing_filters_out_wrong_carrier():
    """Test marks iio_carrier=['zc706'] but the only live ad9081 place is on
    zcu102 → no entries."""
    markers = {
        "t::a": MarkerSpec.of(["ad9081"], iio_carrier=["zc706"]),
    }
    places = [_place("mini2", "ad9081", carrier="zcu102")]
    assert intersect(markers, places) == []


def test_carrier_narrowing_passes_when_carrier_matches():
    markers = {
        "t::a": MarkerSpec.of(["ad9081"], iio_carrier=["zcu102"]),
    }
    places = [_place("mini2", "ad9081", carrier="zcu102")]
    entries = intersect(markers, places)
    assert len(entries) == 1


def test_test_lists_multiple_daughters_runs_on_either():
    """A test marked [ad9081, ad9081_tdd] should run on either."""
    markers = {"t::a": MarkerSpec.of(["ad9081", "ad9081_tdd"])}
    places = [
        _place("mini2", "ad9081"),
        _place("tdd_lab", "ad9081_tdd"),
    ]
    entries = intersect(markers, places)
    assert {e.place for e in entries} == {"mini2", "tdd_lab"}


def test_acquired_places_skipped_by_default():
    markers = {"t::a": MarkerSpec.of(["ad9081"])}
    places = [_place("mini2", "ad9081", acquired="ci-host/runner-1")]
    assert intersect(markers, places) == []


def test_acquired_places_included_when_asked():
    markers = {"t::a": MarkerSpec.of(["ad9081"])}
    places = [_place("mini2", "ad9081", acquired="ci-host/runner-1")]
    entries = intersect(markers, places, skip_acquired=False)
    assert len(entries) == 1


def test_no_match_yields_empty():
    """Marker wants ad9081, only adrv9009 available."""
    markers = {"t::a": MarkerSpec.of(["ad9081"])}
    places = [_place("nemo", "adrv9009")]
    assert intersect(markers, places) == []


def test_as_matrix_dict_shape():
    markers = {"t::a": MarkerSpec.of(["ad9081"])}
    places = [_place("mini2", "ad9081", hdl_config="m8_l4")]
    e = intersect(markers, places)[0]
    d = e.as_matrix_dict()
    # Required keys for GHA matrix include
    for key in (
        "place",
        "carrier",
        "daughter_board",
        "boot_strategy",
        "marker_filter",
        "tests",
        "hdl_config",
    ):
        assert key in d
    assert d["hdl_config"] == "m8_l4"
