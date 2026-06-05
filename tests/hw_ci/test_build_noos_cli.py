from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod


def test_build_noos_cmd_parses_build_vars(monkeypatch):
    captured = {}

    def fake_build_noos(**kw):
        captured.update(kw)
        return {"elf": "/x/ad9371.elf", "bitstream": "/x/b.bit", "ps7_init": "/x/p.tcl"}

    monkeypatch.setattr(cli_mod, "build_noos", fake_build_noos, raising=False)

    args = SimpleNamespace(
        project="ad9371",
        carrier="zc706",
        board="adrv9371",
        release="2023_R2_P1",
        validate="Done",
        build_var=["EXAMPLE=iio_example", "TINYIIOD=y"],
        noos_root=".",
        xsa_dir=None,
    )
    rc = cli_mod._cmd_build_noos(args)
    assert rc == 0
    assert captured["project"] == "ad9371"
    assert captured["build_vars"] == {"EXAMPLE": "iio_example", "TINYIIOD": "y"}


def test_build_noos_dispatches_through_main(monkeypatch):
    seen = {}

    def fake_build_noos(**kw):
        seen.update(kw)
        return {"elf": "/x/ad9371.elf", "bitstream": "/x/b.bit", "ps7_init": "/x/p.tcl"}

    monkeypatch.setattr(cli_mod, "build_noos", fake_build_noos, raising=False)
    rc = cli_mod.main(
        [
            "build-noos",
            "--project",
            "ad9371",
            "--carrier",
            "zc706",
            "--board",
            "adrv9371",
            "--release",
            "2023_R2_P1",
            "--build-var",
            "EXAMPLE=iio_example",
        ]
    )
    assert rc == 0
    assert seen["project"] == "ad9371"
    assert seen["build_vars"] == {"EXAMPLE": "iio_example"}
