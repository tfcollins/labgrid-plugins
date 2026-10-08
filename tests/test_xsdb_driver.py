"""Unit tests for XSDBDriver."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.xsdbdriver import XSDBDriver


@pytest.fixture
def driver():
    """Create an XSDBDriver instance bypassing full target resolution."""
    d = XSDBDriver.__new__(XSDBDriver)
    d.target = MagicMock()
    d.target.env = None
    d.name = "xsdb"
    d.logger = logging.getLogger("test_xsdb_driver")
    d.interface = MagicMock(host=None, serial="", agent_url="", bitstream_path=None)
    d.bitstream = None
    d.state = BindingState.active
    d.xsdb_bin = "xsdb"
    return d


def test_resolve_connect_command(driver, monkeypatch):
    # Default without host or agent_url
    assert driver._resolve_connect_command() == "connect"

    # With host only when remote: xsdb runs on exporter via SSH so connect is local to exporter
    driver.interface.host = "192.168.1.50"
    assert driver._resolve_connect_command() == "connect"

    # With host only when forced local: connects to exporter over TCP
    monkeypatch.setenv("LG_FORCE_LOCAL_XSDB", "1")
    assert driver._resolve_connect_command() == "connect -url tcp:192.168.1.50:3121"
    monkeypatch.delenv("LG_FORCE_LOCAL_XSDB")

    # With explicit agent_url
    driver.interface.agent_url = "tcp:10.0.0.1:3121"
    assert driver._resolve_connect_command() == "connect -url tcp:10.0.0.1:3121"

    # With wildcard agent_url tcp::3121 + host substitution
    driver.interface.agent_url = "tcp::3121"
    driver.interface.host = "192.168.1.50"
    assert driver._resolve_connect_command() == "connect -url tcp:192.168.1.50:3121"


@patch("subprocess.run")
def test_run_local(mock_run, driver):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    out = driver.run(["targets 1", "mrd 0x0"])
    assert out == "OK"

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "xsdb"
    assert cmd[1] == "-quiet"
    assert cmd[2] == "-eval"
    tcl = cmd[3]
    assert "connect" in tcl
    assert "targets 1" in tcl
    assert "mrd 0x0" in tcl
    assert "disconnect" in tcl


@patch("subprocess.run")
def test_run_with_serial(mock_run, driver):
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    driver.interface.serial = "210308A567B1"
    driver.run(["targets 1"])

    tcl = mock_run.call_args[0][0][3]
    assert 'catch {jtag targets -filter {serial == "210308A567B1"}}' in tcl


@patch.object(XSDBDriver, "run")
def test_program_bitstream(mock_run, driver):
    driver.bitstream = "/tmp/system.bit"
    driver.program_bitstream()
    mock_run.assert_called_once_with(["fpga /tmp/system.bit"])


@patch.object(XSDBDriver, "run")
def test_program_bitstream_from_interface(mock_run, driver):
    driver.interface.bitstream_path = "/tmp/fallback.bit"
    driver.program_bitstream()
    mock_run.assert_called_once_with(["fpga /tmp/fallback.bit"])


def test_program_bitstream_missing_raises(driver):
    with pytest.raises(ExecutionError, match="No bitstream filename provided"):
        driver.program_bitstream()


@patch.object(XSDBDriver, "run")
def test_load_and_run_elf(mock_run, driver):
    driver.load_and_run_elf(
        elf_path="/tmp/test.elf",
        bitstream_path="/tmp/test.bit",
        ps7_init_tcl="/tmp/ps7_init.tcl",
    )
    mock_run.assert_called_once()
    cmds = mock_run.call_args[0][0]
    assert 'targets -set -filter {name =~ "*Cortex-A9 MPCore #0"}' in cmds[0]
    assert "rst -system" in cmds[1]
    assert "fpga -f /tmp/test.bit" in cmds[3]
    assert "source /tmp/ps7_init.tcl" in cmds[5]
    assert "ps7_init" in cmds[6]
    assert "dow /tmp/test.elf" in cmds[8]
    assert "con" in cmds[9]


@patch.object(XSDBDriver, "run")
def test_force_bootmode_reset(mock_run, driver):
    driver.force_bootmode_reset("jtag")
    mock_run.assert_called_once()
    cmds = mock_run.call_args[0][0]
    assert any("mwr 0xff5e0200 0x0100" in cmd for cmd in cmds)

    with pytest.raises(KeyError, match="invalid boot mode"):
        driver.force_bootmode_reset("invalid_mode")


@patch.object(XSDBDriver, "program_bitstream")
@patch.object(XSDBDriver, "load_and_run_elf")
def test_bootstrap_protocol_load(mock_load_elf, mock_program_bit, driver):
    driver.load("/tmp/boot.bit")
    mock_program_bit.assert_called_once_with("/tmp/boot.bit")
    mock_load_elf.assert_not_called()

    driver.load("/tmp/firmware.elf")
    mock_load_elf.assert_called_once_with("/tmp/firmware.elf")
