from adi_lg_plugins.hw_ci import all_places as ap
from adi_lg_plugins.hw_ci.all_places import (
    BootLeg,
    build_all_places_matrix,
    default_reachable,
    host_reachable,
)
from adi_lg_plugins.hw_ci.schema import Place


def _place(
    name, daughter, carrier, strategy="BootFPGASoC", runner="hw-x", acquired=None, exporter=None
):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy=strategy,
        acquired=acquired,
        exporter=exporter,
        extra_tags={"runner": runner} if runner else {},
    )


def test_uri_bootable_place_becomes_a_uri_leg():
    legs, acquired, unreachable = build_all_places_matrix(
        [_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")]
    )
    assert acquired == []
    assert unreachable == []
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
    legs, _, _ = build_all_places_matrix(
        [_place("jtagbox", "adrv9371", "zc706", strategy="BootNoOSJTAG")]
    )
    assert legs[0].mode == "reserve"


def test_unknown_strategy_defaults_to_reserve():
    legs, _, _ = build_all_places_matrix(
        [_place("fabricbox", "adrv9371", "zc706", strategy="BootFabric")]
    )
    assert legs[0].mode == "reserve"


def test_acquired_place_is_skipped_and_reported():
    legs, acquired, unreachable = build_all_places_matrix(
        [_place("busy", "ad9081", "vcu118", acquired="someone")]
    )
    assert legs == []
    assert acquired == ["busy"]
    assert unreachable == []


def test_missing_runner_tag_yields_none_runner():
    legs, _, _ = build_all_places_matrix([_place("x", "adrv9002", "zcu102", runner=None)])
    assert legs[0].runner is None


def test_as_matrix_dict_shape():
    legs, _, _ = build_all_places_matrix([_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")])
    assert legs[0].as_matrix_dict() == {
        "place": "mini2",
        "part": "adrv9002",
        "carrier": "zcu102",
        "runner": "hw-mini2",
        "boot_strategy": "BootFPGASoC",
        "mode": "uri",
    }


def test_no_reachable_predicate_keeps_every_place():
    # reachable=None (the default) means no probing — an unreachable-looking place
    # still gets a leg. This preserves behavior for callers that don't opt in.
    legs, _, unreachable = build_all_places_matrix(
        [_place("down", "daq3", "vcu118", exporter="down")]
    )
    assert unreachable == []
    assert [leg.place for leg in legs] == ["down"]


def test_unreachable_place_is_dropped_when_predicate_rejects_it():
    places = [
        _place("up", "adrv9002", "zcu102", exporter="up"),
        _place("down", "daq3", "vcu118", exporter="down"),
    ]
    legs, _, unreachable = build_all_places_matrix(places, reachable=lambda p: p.exporter != "down")
    assert [leg.place for leg in legs] == ["up"]
    assert unreachable == ["down"]


def test_acquired_takes_precedence_over_reachability_check():
    # An acquired place is contention, reported separately, and never probed.
    probed = []

    def reachable(p):
        probed.append(p.name)
        return True

    legs, acquired, unreachable = build_all_places_matrix(
        [_place("busy", "ad9081", "vcu118", acquired="someone", exporter="busy")],
        reachable=reachable,
    )
    assert acquired == ["busy"]
    assert unreachable == []
    assert probed == []  # acquired short-circuits before the reachability probe


def test_default_reachable_treats_unknown_exporter_as_reachable(monkeypatch):
    # No exporter host to probe -> must not be dropped (can't prove it's down).
    monkeypatch.setattr(ap, "host_reachable", lambda *a, **k: False)
    assert default_reachable(_place("x", "adrv9002", "zcu102", exporter=None)) is True


def test_default_reachable_probes_the_exporter_host(monkeypatch):
    seen = {}

    def fake(host, **kw):
        seen["host"] = host
        return False

    monkeypatch.setattr(ap, "host_reachable", fake)
    assert default_reachable(_place("nuc", "daq3", "vcu118", exporter="nuc")) is False
    assert seen["host"] == "nuc"


def test_host_reachable_tries_bare_then_dot_local(monkeypatch):
    attempted = []

    def fake_conn(addr, timeout=None):
        attempted.append(addr[0])
        if addr[0].endswith(".local"):

            class _S:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

            return _S()
        raise OSError("name resolution failed")

    monkeypatch.setattr(ap.socket, "create_connection", fake_conn)
    assert host_reachable("bq") is True
    assert attempted == ["bq", "bq.local"]  # bare first, then mDNS fallback


def test_host_reachable_false_when_both_forms_fail(monkeypatch):
    def fake_conn(addr, timeout=None):
        raise OSError("unreachable")

    monkeypatch.setattr(ap.socket, "create_connection", fake_conn)
    assert host_reachable("nuc") is False
