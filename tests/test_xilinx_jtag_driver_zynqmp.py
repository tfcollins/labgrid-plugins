"""Unit tests for XilinxJTAGDriver ZynqMP (UltraScale+) helpers."""

import logging
from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.xilinxjtagdriver import XilinxJTAGDriver


@pytest.fixture
def driver():
    """Construct an XilinxJTAGDriver bypassing labgrid binding machinery.

    Mirrors tests/test_xilinx_jtag_driver_zynq.py: sidestep ``__init__`` so we
    don't need a real Target, and capture the emitted TCL via a fake
    ``_run_xsdb``.
    """
    d = XilinxJTAGDriver.__new__(XilinxJTAGDriver)
    d.target = MagicMock()
    d.target.resources = []
    d.name = "jtag"
    d.logger = logging.getLogger("test_xilinx_jtag_zynqmp")
    d.xilinxvivado = MagicMock(xsdb_path="xsdb")
    d.xilinxdevicejtag = MagicMock()
    d.state = BindingState.active
    d._captured = []

    def _fake(tcl):
        d._captured.append(tcl)
        return ("", "", 0)

    d._run_xsdb = _fake
    return d


def test_load_zynqmp_uboot_basic(driver):
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl")
    tcl = driver._captured[0]
    assert "connect -url TCP:127.0.0.1:3121" in tcl
    assert "configparams force-mem-accesses 1" in tcl
    # APU release: bootloop at RVBAR then poke RST_FPD_APU.
    assert "mwr 0xffff0000 0x14000000" in tcl
    assert "mwr 0xFD1A0104 0x380E" in tcl
    # psu_init bring-up.
    assert "source /tmp/psu_init.tcl" in tcl
    assert "psu_init" in tcl
    assert "psu_post_config" in tcl
    assert "psu_ps_pl_isolation_removal" in tcl
    # Clean core + download SPL + run.
    assert "rst -processor -clear-registers" in tcl
    assert "dow /tmp/u-boot-spl" in tcl
    assert "con" in tcl


def test_load_zynqmp_uboot_no_bitstream_omits_fpga_line(driver):
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl")
    assert "fpga -file" not in driver._captured[0]


def test_load_zynqmp_uboot_includes_bitstream_before_psu_init(driver):
    driver.load_zynqmp_uboot(
        "/tmp/psu_init.tcl",
        "/tmp/u-boot-spl",
        bitstream_path="/tmp/system_top.bit",
    )
    tcl = driver._captured[0]
    assert "fpga -file /tmp/system_top.bit" in tcl
    # PL must be up before psu_init when the PS init depends on it.
    assert tcl.index("fpga -file /tmp/system_top.bit") < tcl.index("psu_init")


def test_load_zynqmp_uboot_downloads_only_spl(driver):
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl")
    # Exactly one ELF is downloaded: the mini SPL (no FSBL/BL31/full-U-Boot).
    assert driver._captured[0].count("dow ") == 1
    assert "dow /tmp/u-boot-spl" in driver._captured[0]


def test_load_zynqmp_uboot_dcc_capture_optional(driver):
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl")
    assert "readjtaguart" not in driver._captured[0]
    driver._captured.clear()
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl", dcc_log_path="/tmp/dcc.log")
    tcl = driver._captured[0]
    assert "readjtaguart -start -handle [open /tmp/dcc.log w]" in tcl
    assert "readjtaguart -stop" in tcl
    # start must precede the bare `con` (resume), stop must follow it.
    con_idx = tcl.index("\n        con\n")
    assert tcl.index("readjtaguart -start") < con_idx
    assert tcl.index("readjtaguart -stop") > con_idx


def test_load_zynqmp_uboot_custom_apu_release_value(driver):
    driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl", apu_release_rst_value="0x0")
    assert "mwr 0xFD1A0104 0x0" in driver._captured[0]


def test_load_zynqmp_uboot_custom_target_name(driver):
    driver.load_zynqmp_uboot(
        "/tmp/psu_init.tcl",
        "/tmp/u-boot-spl",
        a53_target_name="*Cortex-A53*#1*",
    )
    assert 'name =~ "*Cortex-A53*#1*"' in driver._captured[0]


def test_load_zynqmp_uboot_raises_on_xsdb_failure(driver):
    driver._run_xsdb = lambda tcl: ("", "DDR init failed", 1)
    with pytest.raises(ExecutionError, match="DDR init failed"):
        driver.load_zynqmp_uboot("/tmp/psu_init.tcl", "/tmp/u-boot-spl")


def test_stop_zynqmp_cpu_emits_stop(driver):
    driver.stop_zynqmp_cpu()
    tcl = driver._captured[0]
    assert "connect" in tcl
    assert 'targets -set -nocase -filter {name =~ "*Cortex-A53*#0*"}' in tcl
    assert "stop" in tcl
