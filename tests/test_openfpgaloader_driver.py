"""Unit tests for OpenFPGALoaderDriver command construction and safety."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.openfpgaloaderdriver import OpenFPGALoaderDriver


def _driver(**overrides):
    driver = OpenFPGALoaderDriver.__new__(OpenFPGALoaderDriver)
    driver.state = BindingState.active
    driver.logger = MagicMock()
    driver.target = MagicMock()
    driver.name = "openfpgaloader"
    driver.tool = overrides.get("tool", "openFPGALoader")
    driver.board = overrides.get("board")
    driver.cable = overrides.get("cable", "ft2232")
    driver.fpga_part = overrides.get("fpga_part", "xc7z035ffg676")
    driver.usb_busnum = overrides.get("usb_busnum")
    driver.usb_devnum = overrides.get("usb_devnum")
    driver.usb_serial = overrides.get("usb_serial")
    driver.frequency = overrides.get("frequency")
    driver.allow_flash = overrides.get("allow_flash", False)
    driver.timeout = overrides.get("timeout", 300)
    driver.interface = overrides.get(
        "interface",
        SimpleNamespace(
            busnum=3,
            devnum=7,
            serial="probe-1",
            vendor_id=0x0403,
            model_id=0x6010,
            wrap_command=lambda command: ["ssh", "exporter", *command],
        ),
    )
    driver._remote_prefix = MagicMock(return_value=["ssh", "exporter"])
    driver._stage_file = MagicMock(return_value="/remote/design.bit")
    driver._cleanup_remote_stage = MagicMock()
    return driver


def test_load_stages_and_programs_sram(monkeypatch, tmp_path):
    bitstream = tmp_path / "design.bit"
    bitstream.write_bytes(b"bit")
    driver = _driver()
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)

    assert driver.load(bitstream) == "ok"
    command = run.call_args.args[0]
    assert command == [
        "ssh",
        "exporter",
        "openFPGALoader",
        "--cable",
        "ft2232",
        "--fpga-part",
        "xc7z035ffg676",
        "--busdev-num",
        "3:7",
        "--vid",
        "0x0403",
        "--pid",
        "0x6010",
        "--write-sram",
        "/remote/design.bit",
    ]
    assert "--write-flash" not in command
    assert run.call_args.kwargs["timeout"] == 300


def test_detect_uses_exact_probe_selector(monkeypatch):
    driver = _driver()
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="found", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    assert driver.detect() == "found"
    assert "--busdev-num" in run.call_args.args[0]
    assert run.call_args.args[0][-1] == "--detect"


def test_detect_returns_success_output_from_stderr(monkeypatch):
    driver = _driver()
    run = MagicMock(
        return_value=SimpleNamespace(returncode=0, stdout="", stderr="model  xc7z035\n")
    )
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)

    assert "xc7z035" in driver.detect()


def test_serial_selector_is_fallback(monkeypatch):
    interface = SimpleNamespace(
        busnum=None,
        devnum=None,
        serial="exact-serial",
        vendor_id=None,
        model_id=None,
        wrap_command=lambda command: command,
    )
    driver = _driver(interface=interface)
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="found", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    driver.detect()
    assert "--usb-serial-num" in run.call_args.args[0]
    assert "exact-serial" in run.call_args.args[0]


def test_explicit_driver_selector_supports_xilinx_resource(monkeypatch):
    interface = SimpleNamespace(
        busnum=None,
        devnum=None,
        serial=None,
        vendor_id=None,
        model_id=None,
    )
    driver = _driver(interface=interface, usb_busnum=5, usb_devnum=9)
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="found", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    driver.detect()
    assert "5:9" in run.call_args.args[0]


def test_ambiguous_probe_is_rejected_before_execution(monkeypatch):
    interface = SimpleNamespace(
        busnum=None,
        devnum=None,
        serial=None,
        vendor_id=None,
        model_id=None,
        wrap_command=lambda command: command,
    )
    driver = _driver(interface=interface)
    run = MagicMock()
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    with pytest.raises(ExecutionError, match="refusing ambiguous probe"):
        driver.detect()
    run.assert_not_called()


def test_flash_requires_double_opt_in(monkeypatch, tmp_path):
    bitstream = tmp_path / "design.bit"
    bitstream.write_bytes(b"bit")
    driver = _driver(allow_flash=False)
    with pytest.raises(ExecutionError, match="flash programming is disabled"):
        driver.program(bitstream, write_flash=True)


def test_explicit_flash_uses_write_flash(monkeypatch, tmp_path):
    bitstream = tmp_path / "design.bit"
    bitstream.write_bytes(b"bit")
    driver = _driver(allow_flash=True)
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    driver.program(bitstream, write_flash=True)
    command = run.call_args.args[0]
    assert "--write-flash" in command
    assert "--write-sram" not in command


def test_missing_bitstream_is_rejected_before_staging(tmp_path):
    driver = _driver()
    with pytest.raises(ExecutionError, match="does not exist"):
        driver.load(tmp_path / "missing.bit")


def test_nonzero_exit_is_bounded(monkeypatch):
    driver = _driver()
    run = MagicMock(return_value=SimpleNamespace(returncode=9, stdout="", stderr="x" * 3000))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    with pytest.raises(ExecutionError) as exc:
        driver.detect()
    assert "exit status 9" in str(exc.value)
    assert len(str(exc.value)) < 2100


# --- bitstreams already on the exporter -------------------------------------


def _with_exporter(driver, *, exists=True, remote=True, monkeypatch=None):
    driver._remote_run = MagicMock(return_value=SimpleNamespace(returncode=0 if exists else 1))
    monkeypatch.setattr(
        OpenFPGALoaderDriver, "_is_remote", property(lambda self: remote), raising=False
    )
    return driver


def _ok_run(monkeypatch):
    run = MagicMock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr("adi_lg_plugins.drivers.openfpgaloaderdriver.subprocess.run", run)
    return run


def test_exporter_prefix_programs_the_exporter_file_without_staging(monkeypatch):
    driver = _with_exporter(_driver(), monkeypatch=monkeypatch)
    run = _ok_run(monkeypatch)

    driver.load("exporter:/srv/recovery/zc706/system_top.bit")

    driver._stage_file.assert_not_called()
    driver._remote_run.assert_called_once_with(["test", "-f", "/srv/recovery/zc706/system_top.bit"])
    command = run.call_args.args[0]
    assert command[-2:] == ["--write-sram", "/srv/recovery/zc706/system_top.bit"]


def test_absolute_path_missing_locally_is_taken_from_a_remote_exporter(monkeypatch):
    # bitstream-path place tags name files on the exporter.
    driver = _with_exporter(_driver(), monkeypatch=monkeypatch)
    run = _ok_run(monkeypatch)

    driver.load("/srv/recovery/zc706/system_top.bit")

    driver._stage_file.assert_not_called()
    assert run.call_args.args[0][-1] == "/srv/recovery/zc706/system_top.bit"


def test_a_local_file_is_still_staged_when_remote(monkeypatch, tmp_path):
    bitstream = tmp_path / "design.bit"
    bitstream.write_bytes(b"bit")
    driver = _with_exporter(_driver(), monkeypatch=monkeypatch)
    run = _ok_run(monkeypatch)

    driver.load(bitstream)

    driver._stage_file.assert_called_once()
    driver._remote_run.assert_not_called()
    assert run.call_args.args[0][-1] == "/remote/design.bit"


def test_exporter_file_that_does_not_exist_is_rejected_before_programming(monkeypatch):
    driver = _with_exporter(_driver(), exists=False, monkeypatch=monkeypatch)
    run = _ok_run(monkeypatch)

    with pytest.raises(ExecutionError, match="does not exist on the exporter"):
        driver.load("exporter:/srv/missing.bit")
    run.assert_not_called()


def test_empty_exporter_path_is_rejected(monkeypatch):
    driver = _with_exporter(_driver(), monkeypatch=monkeypatch)
    with pytest.raises(ExecutionError, match="must not be empty"):
        driver.load("exporter:")


def test_missing_absolute_path_is_rejected_when_local(monkeypatch, tmp_path):
    driver = _with_exporter(_driver(), remote=False, monkeypatch=monkeypatch)
    with pytest.raises(ExecutionError, match="bitstream does not exist"):
        driver.load(tmp_path / "missing.bit")
    driver._remote_run.assert_not_called()


def test_flash_opt_in_is_checked_before_touching_the_exporter(monkeypatch):
    driver = _with_exporter(_driver(), monkeypatch=monkeypatch)
    with pytest.raises(ExecutionError, match="allow_flash"):
        driver.program("exporter:/srv/x.bit", write_flash=True)
    driver._remote_run.assert_not_called()
