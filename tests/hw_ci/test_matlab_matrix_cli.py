import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, runner):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
        extra_tags={"runner": runner},
    )


def test_matlab_matrix_emits_legs_for_mapped_places(tmp_path, monkeypatch, capsys):
    board_map = tmp_path / "board_map.yaml"
    board_map.write_text(
        "boards:\n"
        "  - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}\n"
    )
    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:20408")

    def fake_list_live_places(coord, **kw):
        return (
            [
                _place("mini2", "adrv9002", "zcu102", "hw-mini2"),
                _place("nuc", "daq3", "vcu118", "hw-nuc"),  # unmapped -> skipped
            ],
            [],
        )

    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", fake_list_live_places)

    args = SimpleNamespace(board_map=str(board_map), coord=None, github_output=False)
    rc = cli_mod._cmd_matlab_matrix(args)
    assert rc == 0

    out = capsys.readouterr()
    leg = json.loads(out.out)["include"][0]
    assert leg == {
        "part": "adrv9002",
        "carrier": "zcu102",
        "runner": "hw-mini2",
        "matlab_board": "zynqmp-zcu102-rev10-adrv9002-vcmos",
    }
    assert "::warning::" in out.err
    assert "nuc" in out.err


def test_matlab_matrix_parser_wires_via_main(monkeypatch, tmp_path):
    board_map = tmp_path / "bm.yaml"
    board_map.write_text("boards: []\n")
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")
    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", lambda *a, **k: ([], []))
    rc = cli_mod.main(["matlab-matrix", "--board-map", str(board_map)])
    assert rc == 0
