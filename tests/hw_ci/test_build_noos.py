import zipfile
from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import build_noos


def test_detect_vivado_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("VITIS_SETTINGS", "/custom/settings64.sh")
    assert build_noos.detect_vivado_settings() == Path("/custom/settings64.sh")


def test_detect_vivado_globs_newest(monkeypatch):
    monkeypatch.delenv("VITIS_SETTINGS", raising=False)
    found = [
        "/opt/Xilinx/Vivado/2023.2/settings64.sh",
        "/opt/Xilinx/Vivado/2025.1/settings64.sh",
    ]
    monkeypatch.setattr(build_noos.glob, "glob", lambda p: found if "opt" in p else [])
    assert build_noos.detect_vivado_settings() == Path(found[-1])


def test_detect_vivado_errors_when_absent(monkeypatch):
    monkeypatch.delenv("VITIS_SETTINGS", raising=False)
    monkeypatch.setattr(build_noos.glob, "glob", lambda p: [])
    with pytest.raises(FileNotFoundError):
        build_noos.detect_vivado_settings()


def test_ensure_libtinfo_shim_idempotent(tmp_path, monkeypatch):
    so6 = tmp_path / "libtinfo.so.6"
    so6.write_bytes(b"")
    monkeypatch.setattr(build_noos, "_find_so6", lambda stem: so6 if stem == "libtinfo" else so6)
    shim = tmp_path / "xlnxshim"

    d1 = build_noos.ensure_libtinfo_shim(str(shim))
    d2 = build_noos.ensure_libtinfo_shim(str(shim))  # second call must not raise
    assert (Path(d1) / "libtinfo.so.5").is_symlink()
    assert d1 == d2


def test_build_noos_orchestration_order(tmp_path, monkeypatch):
    noos_root = tmp_path
    proj_dir = noos_root / "projects" / "ad9371"
    proj_dir.mkdir(parents=True)

    # a fake .xsa (a zip carrying ps7_init.tcl + system_top.bit)
    xsa = tmp_path / "system_top.xsa"
    with zipfile.ZipFile(xsa, "w") as z:
        z.writestr("ps7_init.tcl", "init")
        z.writestr("system_top.bit", "bits")

    monkeypatch.setattr(build_noos, "fetch_board_xsa", lambda *a, **k: xsa)
    monkeypatch.setattr(build_noos, "detect_vivado_settings", lambda: Path("/x/settings64.sh"))
    monkeypatch.setattr(build_noos, "source_env", lambda s: {"XILINX_VIVADO": "/x"})
    monkeypatch.setattr(build_noos, "ensure_libtinfo_shim", lambda: tmp_path / "shim")

    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        calls["env"] = kw.get("env")
        calls["cwd"] = kw.get("cwd")
        # simulate the .elf the build produces
        (proj_dir / "build").mkdir(exist_ok=True)
        (proj_dir / "build" / "ad9371.elf").write_bytes(b"elf")

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(build_noos.subprocess, "run", fake_run)

    arts = build_noos.build_noos(
        project="ad9371",
        carrier="zc706",
        board="adrv9371",
        release="2023_R2_P1",
        build_vars={"EXAMPLE": "iio_example"},
        noos_root=str(noos_root),
    )

    # .xsa copied into the project; bit + ps7_init extracted to build_hw/
    assert (proj_dir / "system_top.xsa").exists()
    assert (proj_dir / "build_hw" / "ps7_init.tcl").exists()
    assert (proj_dir / "build_hw" / "system_top.bit").exists()
    # make invoked in the project dir with the build var + composed env
    assert calls["cmd"][:3] == ["make", "-C", str(proj_dir)]
    assert "EXAMPLE=iio_example" in calls["cmd"]
    assert calls["env"]["NOOS_VITIS_HSI_FLOW"] == "1"
    assert calls["env"]["XILINX_VIVADO"] == "/x"
    assert str(tmp_path / "shim") in calls["env"]["LD_LIBRARY_PATH"]
    assert Path(arts["elf"]).name == "ad9371.elf"
    assert Path(arts["bitstream"]).name == "system_top.bit"
    assert Path(arts["ps7_init"]).name == "ps7_init.tcl"
