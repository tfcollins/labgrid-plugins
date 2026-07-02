import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import all_places as ap_mod
from adi_lg_plugins.hw_ci import cli as cli_mod
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
        extra_tags={"runner": runner},
    )


def test_all_places_matrix_emits_one_leg_per_free_place(monkeypatch, capsys):
    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:20408")
    monkeypatch.setattr(
        cli_mod.coord_mod,
        "list_live_places",
        lambda *a, **k: (
            [
                _place("mini2", "adrv9002", "zcu102", runner="hw-mini2"),
                _place("busy", "ad9081", "vcu118", acquired="someone"),
            ],
            [],
        ),
    )
    rc = cli_mod._cmd_all_places_matrix(
        SimpleNamespace(coord=None, github_output=False, check_reachability=False)
    )
    assert rc == 0
    out = capsys.readouterr()
    include = json.loads(out.out)["include"]
    assert include == [
        {
            "place": "mini2",
            "part": "adrv9002",
            "carrier": "zcu102",
            "runner": "hw-mini2",
            "boot_strategy": "BootFPGASoC",
            "mode": "uri",
        }
    ]
    assert "::notice::" in out.err and "busy" in out.err


def test_all_places_matrix_fails_when_no_live_places(monkeypatch, capsys):
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")
    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", lambda *a, **k: ([], []))
    rc = cli_mod._cmd_all_places_matrix(
        SimpleNamespace(coord=None, github_output=False, check_reachability=False)
    )
    assert rc == 3
    assert "no-live-places" in capsys.readouterr().err


def test_all_places_matrix_fails_when_coordinator_unreachable(monkeypatch, capsys):
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", boom)
    rc = cli_mod._cmd_all_places_matrix(
        SimpleNamespace(coord=None, github_output=False, check_reachability=False)
    )
    assert rc == 3
    assert "coordinator-unreachable" in capsys.readouterr().err


def test_boot_junit_writes_file(tmp_path):
    out = tmp_path / "results-mini2.xml"
    rc = cli_mod.main(
        [
            "boot-junit",
            "--place",
            "mini2",
            "--part",
            "adrv9002",
            "--carrier",
            "zcu102",
            "--mode",
            "uri",
            "--status",
            "pass",
            "--seconds",
            "42",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert 'name="uri:adrv9002@mini2"' in text
    assert 'failures="0"' in text


def test_boot_junit_writes_skip_file(tmp_path):
    out = tmp_path / "results-mini2.xml"
    rc = cli_mod.main(
        [
            "boot-junit",
            "--place",
            "mini2",
            "--part",
            "adrv9002",
            "--carrier",
            "zcu102",
            "--mode",
            "uri",
            "--status",
            "skip",
            "--seconds",
            "3",
            "--message",
            "adi-lg request exit 11",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    text = out.read_text(encoding="utf-8")
    assert 'skipped="1"' in text


def test_all_places_matrix_drops_unreachable_with_check_reachability(monkeypatch, capsys):
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")
    monkeypatch.setattr(
        cli_mod.coord_mod,
        "list_live_places",
        lambda *a, **k: (
            [
                _place("up", "adrv9002", "zcu102", runner="hw-up", exporter="up"),
                _place("down", "daq3", "vcu118", runner="hw-down", exporter="down"),
            ],
            [],
        ),
    )
    # Probe: only "up" answers; "down" (offline host) does not. default_reachable
    # resolves host_reachable from the all_places module namespace at call time.
    monkeypatch.setattr(ap_mod, "host_reachable", lambda h, **k: h == "up")
    rc = cli_mod._cmd_all_places_matrix(
        SimpleNamespace(coord=None, github_output=False, check_reachability=True)
    )
    assert rc == 0
    out = capsys.readouterr()
    assert [leg["place"] for leg in json.loads(out.out)["include"]] == ["up"]
    assert "::warning::" in out.err and "down" in out.err and "unreachable" in out.err


def test_all_places_matrix_wires_via_main(monkeypatch):
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")
    monkeypatch.setattr(
        cli_mod.coord_mod,
        "list_live_places",
        lambda *a, **k: ([_place("m", "adrv9002", "zcu102")], []),
    )
    assert cli_mod.main(["all-places-matrix"]) == 0
