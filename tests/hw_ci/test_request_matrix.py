from __future__ import annotations

import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as hw_cli
from adi_lg_plugins.hw_ci.request_matrix import MatrixLeg, RequestMatrix, build_request_matrix


def _match(satisfiable, runner=None):
    """A minimal stand-in for a /api/match result (duck-typed)."""
    return SimpleNamespace(satisfiable=satisfiable, runner=runner)


# ---- pure builder ----


def test_build_splits_available_and_missing_with_runner():
    avail = {"adrv9002": "hw-mini2", "ad9081": "hw-nuc"}

    def probe(p):
        return _match(p in avail, runner=avail.get(p))

    r = build_request_matrix(["ad9081", "adrv9002", "ad9361"], probe)
    assert isinstance(r, RequestMatrix)
    # available, sorted, each carrying its co-located runner label
    assert r.parts == [
        MatrixLeg(part="ad9081", runner="hw-nuc"),
        MatrixLeg(part="adrv9002", runner="hw-mini2"),
    ]
    assert r.missing == ["ad9361"]  # wanted but no live board


def test_build_dedupes_and_sorts():
    r = build_request_matrix(["b", "a", "a"], lambda p: _match(True, runner=f"hw-{p}"))
    assert [leg.part for leg in r.parts] == ["a", "b"]
    assert r.missing == []


def test_build_all_missing():
    r = build_request_matrix(["x"], lambda p: _match(False))
    assert r.parts == []
    assert r.missing == ["x"]


def test_build_satisfiable_without_runner_tag_yields_none_runner():
    r = build_request_matrix(["x"], lambda p: _match(True, runner=None))
    assert r.parts == [MatrixLeg(part="x", runner=None)]


def test_build_probe_returning_none_is_treated_as_missing():
    r = build_request_matrix(["x"], lambda p: None)
    assert r.parts == []
    assert r.missing == ["x"]


# ---- CLI subcommand (monkeypatched: no coordinator, no test files) ----


def test_request_matrix_cli_emits_matrix_and_annotates(monkeypatch, capsys):
    from adi_lg_plugins.hw_ci import coordinator as coord_mod
    from adi_lg_plugins.hw_ci import markers as markers_mod
    from adi_lg_plugins.request import match_client

    monkeypatch.setattr(coord_mod, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(
        markers_mod,
        "harvest_markers",
        lambda root, marker="iio_hardware": {
            "t1": SimpleNamespace(iio_hardware=frozenset({"adrv9002"})),
            "t2": SimpleNamespace(iio_hardware=frozenset({"ad9361"})),
        },
    )
    available = {"adrv9002": "hw-mini2"}
    monkeypatch.setattr(
        match_client,
        "get_match",
        lambda coord, *, part, **k: SimpleNamespace(
            satisfiable=part in available, runner=available.get(part)
        ),
    )

    rc = hw_cli.main(["request-matrix", "--test-root", "test", "--coord", "coord:8000"])
    assert rc == 0

    out = capsys.readouterr()
    # each leg carries the runner label its board is co-located with
    assert json.loads(out.out) == {"include": [{"part": "adrv9002", "runner": "hw-mini2"}]}
    assert "::warning::" in out.err
    assert "ad9361" in out.err


def test_request_matrix_cli_probe_failure_treated_as_unavailable(monkeypatch, capsys):
    from adi_lg_plugins.hw_ci import coordinator as coord_mod
    from adi_lg_plugins.hw_ci import markers as markers_mod
    from adi_lg_plugins.request import match_client

    monkeypatch.setattr(coord_mod, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(
        markers_mod,
        "harvest_markers",
        lambda root, marker="iio_hardware": {
            "t1": SimpleNamespace(iio_hardware=frozenset({"adrv9002"}))
        },
    )

    def boom(coord, *, part, **k):
        raise RuntimeError("coordinator unreachable")

    monkeypatch.setattr(match_client, "get_match", boom)
    rc = hw_cli.main(["request-matrix", "--test-root", "test", "--coord", "coord:8000"])
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"include": []}
