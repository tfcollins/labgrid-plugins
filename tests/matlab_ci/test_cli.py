"""Tests for adi_lg_plugins.matlab_ci.cli."""

from __future__ import annotations

import json
import textwrap

import pytest

from adi_lg_plugins.hw_ci.schema import Place
from adi_lg_plugins.matlab_ci import cli
from adi_lg_plugins.matlab_ci.run import MatlabRunResult


def _board_map_file(tmp_path):
    f = tmp_path / "board_map.yaml"
    f.write_text(
        textwrap.dedent(
            """
            boards:
              - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
            """
        ),
        encoding="utf-8",
    )
    return f


def _place(name="mini2", daughter="adrv9002"):
    return Place(
        name=name,
        carrier="zcu102",
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
    )


# --- discover ------------------------------------------------------------


def test_discover_emits_matrix_and_github_output(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli.coord_mod, "list_live_places", lambda *a, **k: ([_place()], []))
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))

    rc = cli.main(
        [
            "discover",
            "--coord",
            "c:1",
            "--board-map",
            str(_board_map_file(tmp_path)),
            "--github-output",
        ]
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["include"][0]["place"] == "mini2"
    assert out["include"][0]["matlab_board"] == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert out["include"][0]["runner_label"] == "hw-mini2"

    gh_text = gh_out.read_text(encoding="utf-8")
    assert "matrix=" in gh_text
    assert "count=1" in gh_text


def test_discover_empty_matrix_when_no_overlap(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        cli.coord_mod,
        "list_live_places",
        lambda *a, **k: ([_place(daughter="ad9081")], []),
    )
    rc = cli.main(["discover", "--coord", "c:1", "--board-map", str(_board_map_file(tmp_path))])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"include": []}


# --- run (config mode) ---------------------------------------------------


def test_run_config_mode_propagates_returncode(tmp_path, monkeypatch):
    cfg = tmp_path / "env.yaml"
    cfg.write_text("targets: {}\n", encoding="utf-8")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return MatlabRunResult(uri="ip:1.2.3.4", matlab_board=kwargs["matlab_board"], returncode=2)

    monkeypatch.setattr(cli, "run_matlab_tests", fake_run)

    rc = cli.main(
        [
            "run",
            "--config",
            str(cfg),
            "--matlab-board",
            "zynqmp-zcu102-rev10-adrv9002-vcmos",
            "--boot-strategy",
            "BootFPGASoC",
            "--repo-dir",
            str(tmp_path),
        ]
    )
    assert rc == 2
    assert captured["matlab_board"] == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert captured["boot_strategy"] == "BootFPGASoC"
    assert str(captured["config"]) == str(cfg)


# --- run (place mode) ----------------------------------------------------


def test_run_place_mode_resolves_board_and_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.coord_mod, "list_live_places", lambda *a, **k: ([_place()], []))
    monkeypatch.setattr(cli.render_mod, "render_env_to", lambda place, out, **k: out)
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return MatlabRunResult(uri="ip:1", matlab_board=kwargs["matlab_board"], returncode=0)

    monkeypatch.setattr(cli, "run_matlab_tests", fake_run)

    rc = cli.main(
        [
            "run",
            "--coord",
            "c:1",
            "--place",
            "mini2",
            "--board-map",
            str(_board_map_file(tmp_path)),
            "--repo-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    # board name comes from the board map; strategy from the place tag
    assert captured["matlab_board"] == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert captured["boot_strategy"] == "BootFPGASoC"


def test_run_place_mode_boot_strategy_override(tmp_path, monkeypatch):
    """--boot-strategy in place mode overrides the place's tag.

    Used when the lab tagged a place with one strategy (e.g.
    BootZynq7000JTAGRecovery) but the consumer wants to drive a
    different one (e.g. BootFPGASoCTFTP) without retagging."""
    monkeypatch.setattr(cli.coord_mod, "list_live_places", lambda *a, **k: ([_place()], []))
    rendered = {}

    def fake_render(place, out, **k):
        rendered["boot_strategy"] = place.boot_strategy
        return out

    monkeypatch.setattr(cli.render_mod, "render_env_to", fake_render)
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return MatlabRunResult(uri="ip:1", matlab_board=kwargs["matlab_board"], returncode=0)

    monkeypatch.setattr(cli, "run_matlab_tests", fake_run)

    rc = cli.main(
        [
            "run",
            "--coord",
            "c:1",
            "--place",
            "mini2",
            "--board-map",
            str(_board_map_file(tmp_path)),
            "--repo-dir",
            str(tmp_path),
            "--boot-strategy",
            "BootFPGASoCTFTP",
        ]
    )
    assert rc == 0
    # override wins for both the rendered template and the run kwarg
    assert rendered["boot_strategy"] == "BootFPGASoCTFTP"
    assert captured["boot_strategy"] == "BootFPGASoCTFTP"


def test_run_place_mode_unknown_board_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cli.coord_mod,
        "list_live_places",
        lambda *a, **k: ([_place(daughter="ad9081")], []),
    )
    rc = cli.main(
        [
            "run",
            "--coord",
            "c:1",
            "--place",
            "mini2",
            "--board-map",
            str(_board_map_file(tmp_path)),
            "--repo-dir",
            str(tmp_path),
        ]
    )
    assert rc != 0  # ad9081 not in the board map


def test_run_acquire_release_order(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.coord_mod, "list_live_places", lambda *a, **k: ([_place()], []))
    monkeypatch.setattr(cli.render_mod, "render_env_to", lambda place, out, **k: out)
    events = []
    monkeypatch.setattr(
        cli, "_acquire_place", lambda coord, place: events.append(("acquire", place))
    )
    monkeypatch.setattr(
        cli, "_release_place", lambda coord, place: events.append(("release", place))
    )

    def fake_run(**kwargs):
        events.append(("run", kwargs["matlab_board"]))
        return MatlabRunResult(uri="ip:1", matlab_board=kwargs["matlab_board"], returncode=0)

    monkeypatch.setattr(cli, "run_matlab_tests", fake_run)

    rc = cli.main(
        [
            "run",
            "--coord",
            "c:1",
            "--place",
            "mini2",
            "--board-map",
            str(_board_map_file(tmp_path)),
            "--repo-dir",
            str(tmp_path),
            "--acquire",
        ]
    )
    assert rc == 0
    assert [e[0] for e in events] == ["acquire", "run", "release"]


def test_run_releases_even_on_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.coord_mod, "list_live_places", lambda *a, **k: ([_place()], []))
    monkeypatch.setattr(cli.render_mod, "render_env_to", lambda place, out, **k: out)
    events = []
    monkeypatch.setattr(cli, "_acquire_place", lambda coord, place: events.append("acquire"))
    monkeypatch.setattr(cli, "_release_place", lambda coord, place: events.append("release"))

    def boom(**kwargs):
        raise RuntimeError("boot failed")

    monkeypatch.setattr(cli, "run_matlab_tests", boom)

    with pytest.raises(RuntimeError):
        cli.main(
            [
                "run",
                "--coord",
                "c:1",
                "--place",
                "mini2",
                "--board-map",
                str(_board_map_file(tmp_path)),
                "--repo-dir",
                str(tmp_path),
                "--acquire",
            ]
        )
    assert events == ["acquire", "release"]
