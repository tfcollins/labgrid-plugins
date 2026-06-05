from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod


def test_fetch_xsa_prints_resolved_path(tmp_path, monkeypatch, capsys):
    fake = tmp_path / "system_top.xsa"
    fake.write_bytes(b"x")

    captured = {}

    def fake_fetch(release, board, carrier, cache_dir=None, *, xsa_dir=None):
        captured.update(
            release=release, board=board, carrier=carrier, cache_dir=cache_dir, xsa_dir=xsa_dir
        )
        return fake

    monkeypatch.setattr(cli_mod, "fetch_board_xsa", fake_fetch, raising=False)

    args = SimpleNamespace(
        release="2023_R2_P1", board="adrv9009", carrier="zc706", out=None, xsa_dir=None
    )
    rc = cli_mod._cmd_fetch_xsa(args)
    assert rc == 0
    assert str(fake) in capsys.readouterr().out
    assert captured["board"] == "adrv9009"


def test_fetch_xsa_dispatches_through_main(monkeypatch, tmp_path):
    fake = tmp_path / "system_top.xsa"
    fake.write_bytes(b"x")
    seen = {}

    def fake_fetch(release, board, carrier, cache_dir=None, *, xsa_dir=None):
        seen.update(release=release, board=board, carrier=carrier, xsa_dir=xsa_dir)
        return fake

    monkeypatch.setattr(cli_mod, "fetch_board_xsa", fake_fetch, raising=False)
    rc = cli_mod.main(
        ["fetch-xsa", "--release", "2023_R2_P1", "--board", "adrv9009", "--carrier", "zc706"]
    )
    assert rc == 0
    assert seen == {
        "release": "2023_R2_P1",
        "board": "adrv9009",
        "carrier": "zc706",
        "xsa_dir": None,
    }
