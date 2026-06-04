from __future__ import annotations

import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as hw_cli
from adi_lg_plugins.hw_ci.noos_manifest import (
    NoOSLeg,
    NoOSProject,
    build_noos_matrix,
    load_noos_manifest,
)


def _match(satisfiable, runner=None):
    return SimpleNamespace(satisfiable=satisfiable, runner=runner)


# ---- manifest loader ----


def test_load_noos_manifest(tmp_path):
    p = tmp_path / "projects.yaml"
    p.write_text(
        """
projects:
  - noos_project: adrv9009
    part: adrv9009
    carriers: [zc706]
  - noos_project: ad9371
    part: ad9371
    carriers: [zc706, zcu102]
"""
    )
    projs = load_noos_manifest(str(p))
    assert projs == [
        NoOSProject(noos_project="adrv9009", part="adrv9009", carriers=["zc706"]),
        NoOSProject(noos_project="ad9371", part="ad9371", carriers=["zc706", "zcu102"]),
    ]


# ---- matrix builder ----


def test_build_noos_matrix_splits_runnable_and_missing():
    projs = [
        NoOSProject("adrv9009", "adrv9009", ["zc706"]),
        NoOSProject("ad9371", "ad9371", ["zc706"]),
        NoOSProject("ad7768", "ad7768", ["maxim"]),  # no flash-capable board
    ]
    live = {("adrv9009", "zc706"): "hw-nemo", ("ad9371", "zc706"): "hw-bq"}

    def probe(part, carrier):
        key = (part, carrier)
        return _match(key in live, runner=live.get(key))

    legs, missing = build_noos_matrix(projs, probe)
    assert legs == [
        NoOSLeg(part="adrv9009", noos_project="adrv9009", carrier="zc706", runner="hw-nemo"),
        NoOSLeg(part="ad9371", noos_project="ad9371", carrier="zc706", runner="hw-bq"),
    ]
    assert missing == ["ad7768"]


def test_build_noos_matrix_picks_first_satisfiable_carrier():
    projs = [NoOSProject("ad9371", "ad9371", ["vcu118", "zc706"])]

    def probe(part, carrier):
        return _match(carrier == "zc706", runner="hw-bq")

    legs, missing = build_noos_matrix(projs, probe)
    assert legs == [NoOSLeg(part="ad9371", noos_project="ad9371", carrier="zc706", runner="hw-bq")]
    assert missing == []


# ---- CLI subcommand ----


def test_noos_matrix_cli_emits_matrix_and_annotates(monkeypatch, capsys, tmp_path):
    from adi_lg_plugins.hw_ci import coordinator as coord_mod
    from adi_lg_plugins.request import match_client

    manifest = tmp_path / "projects.yaml"
    manifest.write_text(
        """
projects:
  - {noos_project: ad9371, part: ad9371, carriers: [zc706]}
  - {noos_project: ad7768, part: ad7768, carriers: [maxim]}
"""
    )
    monkeypatch.setattr(coord_mod, "resolve_coordinator", lambda c: "coord:8000")
    live = {("ad9371", "zc706"): "hw-bq"}

    def fake_get_match(coord, *, part, carrier=None, mode="uri", **k):
        assert mode == "flash"
        return SimpleNamespace(satisfiable=(part, carrier) in live, runner=live.get((part, carrier)))

    monkeypatch.setattr(match_client, "get_match", fake_get_match)

    rc = hw_cli.main(
        ["noos-matrix", "--manifest", str(manifest), "--coord", "coord:8000"]
    )
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {
        "include": [
            {"part": "ad9371", "noos_project": "ad9371", "carrier": "zc706", "runner": "hw-bq"}
        ]
    }
    assert "::warning::" in out.err
    assert "ad7768" in out.err
