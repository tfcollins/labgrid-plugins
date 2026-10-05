"""Unit tests for XilinxJTAGDriver compatibility with XilinxUSBJTAG and XSDB features."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.xilinxjtagdriver import XilinxJTAGDriver


@pytest.fixture
def driver():
    """Create an XilinxJTAGDriver instance bypassing labgrid binding resolution."""
    d = XilinxJTAGDriver.__new__(XilinxJTAGDriver)
    d.target = MagicMock()
    d.target.env = None
    d.name = "jtag"
    d.logger = logging.getLogger("test_xilinx_jtag_compat")
    d.xilinxvivado = None
    d.xilinxdevicejtag = MagicMock(
        spec=["host", "agent_url", "serial", "root_target", "microblaze_target"]
    )
    d.xilinxdevicejtag.host = None
    d.xilinxdevicejtag.agent_url = ""
    d.xilinxdevicejtag.serial = ""
    d.xilinxdevicejtag.root_target = 1
    d.xilinxdevicejtag.microblaze_target = 3
    d.state = BindingState.active
    d.staged = []
    d.scripts = []

    def stage(path):
        d.staged.append(path)
        return path

    def run(tcl_script, timeout=300):
        d.scripts.append(tcl_script)
        return "", "", 0

    d._stage_file = stage
    d._run_xsdb = run
    return d


def test_bindings_definition():
    bindings = XilinxJTAGDriver.bindings
    assert "xilinxdevicejtag" in bindings
    assert "XilinxUSBJTAG" in bindings["xilinxdevicejtag"]
    assert "NetworkXilinxUSBJTAG" in bindings["xilinxdevicejtag"]
    assert "USBDebugger" in bindings["xilinxdevicejtag"]
    assert "NetworkUSBDebugger" in bindings["xilinxdevicejtag"]
    assert "XilinxDeviceJTAG" in bindings["xilinxdevicejtag"]

    assert "xilinxvivado" in bindings
    assert None in bindings["xilinxvivado"]
    assert "XilinxVivadoTool" in bindings["xilinxvivado"]


def test_interface_alias(driver):
    assert driver.interface is driver.xilinxdevicejtag


def test_get_xsdb_bin_without_vivado_tool(driver):
    assert driver._get_xsdb_bin() == "xsdb"

    driver.xilinxvivado = MagicMock(xsdb_path="/opt/Xilinx/Vivado/bin/xsdb")
    assert driver._get_xsdb_bin() == "/opt/Xilinx/Vivado/bin/xsdb"


def test_resolve_connect_command_agent_url(driver):
    driver.xilinxdevicejtag.agent_url = "tcp:192.168.1.10:3121"
    assert driver._resolve_connect_command() == "connect -url tcp:192.168.1.10:3121"


def test_resolve_target_select_command(driver):
    assert driver._resolve_target_select_command() == ""

    driver.xilinxdevicejtag.serial = "210308A567B1"
    assert (
        driver._resolve_target_select_command()
        == 'catch {jtag targets -filter {serial == "210308A567B1"}}'
    )


def test_force_bootmode_reset(driver):
    driver.force_bootmode_reset("jtag")
    tcl = driver.scripts[0]
    assert "mwr 0xff5e0200 0" in tcl
    assert "rst -system" in tcl

    driver.scripts.clear()
    driver.force_bootmode_reset("sd_0")
    tcl = driver.scripts[0]
    assert "mwr 0xff5e0200 3" in tcl

    with pytest.raises(ExecutionError, match="Unsupported bootmode"):
        driver.force_bootmode_reset("invalid")


@patch.object(XilinxJTAGDriver, "program_bitstream")
@patch.object(XilinxJTAGDriver, "load_and_run_elf")
def test_bootstrap_protocol_load(mock_load_elf, mock_program_bit, driver):
    driver.load("/tmp/design.bit")
    mock_program_bit.assert_called_once_with("/tmp/design.bit")
    mock_load_elf.assert_not_called()

    driver.load("/tmp/firmware.elf")
    mock_load_elf.assert_called_once_with(elf_path="/tmp/firmware.elf")

    with pytest.raises(ValueError, match="unsupported bootstrap file format"):
        driver.load("/tmp/unknown.txt")
