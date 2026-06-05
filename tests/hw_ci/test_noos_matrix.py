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
        NoOSProject(noos_project="adrv9009", part="adrv9009", carriers=["zc706"]),
        NoOSProject(noos_project="ad9371", part="ad9371", carriers=["zc706"]),
        NoOSProject(
            noos_project="ad7768", part="ad7768", carriers=["maxim"]
        ),  # no flash-capable board
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
    projs = [NoOSProject(noos_project="ad9371", part="ad9371", carriers=["vcu118", "zc706"])]

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
        return SimpleNamespace(
            satisfiable=(part, carrier) in live, runner=live.get((part, carrier))
        )

    monkeypatch.setattr(match_client, "get_match", fake_get_match)

    rc = hw_cli.main(["noos-matrix", "--manifest", str(manifest), "--coord", "coord:8000"])
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {
        "include": [
            {
                "part": "ad9371",
                "noos_project": "ad9371",
                "carrier": "zc706",
                "runner": "hw-bq",
                "board": "",
                "release": "",
                "validate_banner": "Successfully initialized",
                "build_vars": {},
            }
        ]
    }
    assert "::warning::" in out.err
    assert "ad7768" in out.err


def test_noos_matrix_emits_enriched_legs(tmp_path, monkeypatch, capsys):
    import json
    from types import SimpleNamespace

    from adi_lg_plugins.hw_ci import cli as cli_mod

    manifest = tmp_path / "projects.yaml"
    manifest.write_text(
        """
projects:
  - noos_project: ad9371
    part: ad9371
    carriers: [zc706]
    validate_banner: "Done"
    build_vars: {EXAMPLE: iio_example}
"""
    )

    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:20408")

    def fake_get_match(api, *, part, carrier=None, mode="uri"):
        return SimpleNamespace(
            satisfiable=True,
            runner="hw-bq",
            image="2023_R2_P1",
            reservation_filter={"daughter-board": "adrv9371", "carrier": "zc706"},
        )

    # _cmd_noos_matrix imports match_client locally -> patch the source module.
    import adi_lg_plugins.request.match_client as mc

    monkeypatch.setattr(mc, "get_match", fake_get_match)

    args = SimpleNamespace(manifest=str(manifest), coord=None, github_output=False)
    rc = cli_mod._cmd_noos_matrix(args)
    assert rc == 0

    out = capsys.readouterr().out
    leg = json.loads(out)["include"][0]
    assert leg == {
        "part": "ad9371",
        "noos_project": "ad9371",
        "carrier": "zc706",
        "runner": "hw-bq",
        "board": "adrv9371",
        "release": "2023_R2_P1",
        "validate_banner": "Done",
        "build_vars": {"EXAMPLE": "iio_example"},
    }
