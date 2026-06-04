"""Unit tests for XilinxJTAGDriver Zynq-7000 helpers."""

import logging
from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.xilinxjtagdriver import XilinxJTAGDriver


@pytest.fixture
def driver():
    """Construct an XilinxJTAGDriver bypassing labgrid binding machinery.

    We sidestep ``__init__`` (and hence ``__attrs_post_init__``) because the
    binding resolution would otherwise demand a real labgrid Target with
    registered resources. Tests set ``_run_xsdb`` to capture the emitted TCL.
    """
    d = XilinxJTAGDriver.__new__(XilinxJTAGDriver)
    d.target = MagicMock()
    d.target.resources = []
    d.name = "jtag"
    d.logger = logging.getLogger("test_xilinx_jtag")
    d.xilinxvivado = MagicMock(xsdb_path="xsdb")
    d.xilinxdevicejtag = MagicMock()
    d.state = BindingState.active
    d._captured = []

    def _fake(tcl):
        d._captured.append(tcl)
        return ("", "", 0)

    d._run_xsdb = _fake
    return d


def test_load_zynq_uboot_basic(driver):
    driver.load_zynq_uboot("/tmp/init.tcl", "/tmp/u-boot.elf")
    tcl = driver._captured[0]
    assert "connect" in tcl
    assert 'targets -set -filter {name =~ "*Cortex-A9 MPCore #0"}' in tcl
    assert "rst -system" in tcl
    assert "source /tmp/init.tcl" in tcl
    assert "ps7_init" in tcl
    assert "ps7_post_config" in tcl
    assert "dow /tmp/u-boot.elf" in tcl
    assert "con" in tcl


def test_load_zynq_uboot_no_bitstream_omits_fpga_line(driver):
    driver.load_zynq_uboot("/tmp/init.tcl", "/tmp/u-boot.elf")
    assert "fpga -f" not in driver._captured[0]


def test_load_zynq_uboot_includes_bitstream(driver):
    driver.load_zynq_uboot(
        "/tmp/init.tcl",
        "/tmp/u-boot.elf",
        bitstream_path="/tmp/board.bit",
    )
    tcl = driver._captured[0]
    assert "fpga -f /tmp/board.bit" in tcl
    # bitstream must be loaded before ps7_init (PL must be up before PS init
    # if the design depends on PL).
    assert tcl.index("fpga -f /tmp/board.bit") < tcl.index("ps7_init")


def test_load_zynq_uboot_no_fsbl_omits_fsbl_dow(driver):
    driver.load_zynq_uboot("/tmp/init.tcl", "/tmp/u-boot.elf")
    # Only u-boot.elf should be downloaded, no FSBL.
    assert driver._captured[0].count("dow ") == 1
    assert "dow /tmp/u-boot.elf" in driver._captured[0]


def test_load_zynq_uboot_includes_fsbl_before_uboot(driver):
    driver.load_zynq_uboot(
        "/tmp/init.tcl",
        "/tmp/u-boot.elf",
        fsbl_elf="/tmp/fsbl.elf",
    )
    tcl = driver._captured[0]
    assert "dow /tmp/fsbl.elf" in tcl
    assert "dow /tmp/u-boot.elf" in tcl
    # FSBL must run before U-Boot is staged.
    assert tcl.index("dow /tmp/fsbl.elf") < tcl.index("dow /tmp/u-boot.elf")


def test_load_zynq_uboot_custom_target_name(driver):
    driver.load_zynq_uboot(
        "/tmp/init.tcl",
        "/tmp/u-boot.elf",
        a9_target_name="*Cortex-A9 MPCore #1",
    )
    assert 'name =~ "*Cortex-A9 MPCore #1"' in driver._captured[0]


def test_load_zynq_uboot_raises_on_xsdb_failure(driver):
    driver._run_xsdb = lambda tcl: ("", "DDR training failed", 1)
    with pytest.raises(ExecutionError, match="DDR training failed"):
        driver.load_zynq_uboot("/tmp/init.tcl", "/tmp/u-boot.elf")


def test_stop_zynq_cpu_emits_stop(driver):
    driver.stop_zynq_cpu()
    tcl = driver._captured[0]
    assert "connect" in tcl
    assert 'targets -set -filter {name =~ "*Cortex-A9 MPCore #0"}' in tcl
    assert "stop" in tcl


# ---------- load_and_run_elf (no-os firmware flash) -----------------------


def test_load_and_run_elf_basic(driver):
    driver.load_and_run_elf("/tmp/fw.elf")
    tcl = driver._captured[0]
    assert "connect" in tcl
    assert 'targets -set -filter {name =~ "*Cortex-A9 MPCore #0"}' in tcl
    assert "rst -system" in tcl
    assert "dow /tmp/fw.elf" in tcl
    assert "con" in tcl


def test_load_and_run_elf_minimal_omits_optional(driver):
    driver.load_and_run_elf("/tmp/fw.elf")
    tcl = driver._captured[0]
    assert "fpga -f" not in tcl
    assert "source " not in tcl
    assert tcl.count("dow ") == 1  # only the firmware, no fsbl/uboot


def test_load_and_run_elf_with_bitstream_and_ps7(driver):
    driver.load_and_run_elf(
        "/tmp/fw.elf", bitstream_path="/tmp/sys.bit", ps7_init_tcl="/tmp/ps7.tcl"
    )
    tcl = driver._captured[0]
    assert "fpga -f /tmp/sys.bit" in tcl
    assert "source /tmp/ps7.tcl" in tcl
    assert "ps7_init" in tcl
    # fabric + PS init must precede the ELF download
    assert tcl.index("fpga -f /tmp/sys.bit") < tcl.index("dow /tmp/fw.elf")
    assert tcl.index("ps7_init") < tcl.index("dow /tmp/fw.elf")


def test_load_and_run_elf_custom_target(driver):
    driver.load_and_run_elf("/tmp/fw.elf", a9_target_name="*Cortex-A53 #0")
    assert '*Cortex-A53 #0' in driver._captured[0]


def test_load_and_run_elf_raises_on_failure(driver):
    driver._run_xsdb = lambda tcl: ("", "xsdb boom", 1)
    with pytest.raises(ExecutionError, match="ELF"):
        driver.load_and_run_elf("/tmp/fw.elf")
