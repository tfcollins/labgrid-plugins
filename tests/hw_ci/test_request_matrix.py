from __future__ import annotations

import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as hw_cli
from adi_lg_plugins.hw_ci.request_matrix import RequestMatrix, build_request_matrix

# ---- pure builder ----


def test_build_splits_available_and_missing():
    avail = {"adrv9002", "ad9081"}
    r = build_request_matrix(["ad9081", "adrv9002", "ad9361"], lambda p: p in avail)
    assert isinstance(r, RequestMatrix)
    assert r.parts == ["ad9081", "adrv9002"]  # available, sorted
    assert r.missing == ["ad9361"]  # wanted but no live board


def test_build_dedupes_and_sorts():
    r = build_request_matrix(["b", "a", "a"], lambda p: True)
    assert r.parts == ["a", "b"]
    assert r.missing == []


def test_build_all_missing():
    r = build_request_matrix(["x"], lambda p: False)
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
    available = {"adrv9002"}
    monkeypatch.setattr(
        match_client,
        "get_match",
        lambda coord, *, part, **k: SimpleNamespace(satisfiable=part in available),
    )

    rc = hw_cli.main(["request-matrix", "--test-root", "test", "--coord", "coord:8000"])
    assert rc == 0

    out = capsys.readouterr()
    assert json.loads(out.out) == {"include": [{"part": "adrv9002"}]}
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
