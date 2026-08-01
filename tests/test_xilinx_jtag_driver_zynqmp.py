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
    d._timeouts = []

    def _fake(tcl_script, timeout=300):
        d._captured.append(tcl_script)
        d._timeouts.append(timeout)
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


def test_load_zynqmp_recovery_linux_uses_physical_payloads(driver):
    driver.load_zynqmp_recovery_linux(
        psu_init_tcl="/tmp/psu_init.tcl",
        trampoline_elf="/tmp/el3-to-el2.elf",
        kernel_image="/tmp/Image-recovery",
        initramfs="/tmp/initramfs.cpio.gz",
        dtb="/tmp/system-recovery.dtb",
        ddr_scrub_elf="/tmp/ddr-ecc-scrub.elf",
        bitstream_path="/tmp/system_top.bit",
        post_init_mask_writes=[("0xFF5E0238", "0x2", "0x0")],
        jtag_url="TCP:tron.local:3121",
    )
    tcl = driver._captured[0]
    assert "connect -url TCP:tron.local:3121" in tcl
    assert "source /tmp/psu_init.tcl" in tcl
    assert tcl.index("fpga -file /tmp/system_top.bit") < tcl.index("source /tmp/psu_init.tcl")
    assert "mask_write 0xFF5E0238 0x2 0x0" in tcl
    assert "dow /tmp/ddr-ecc-scrub.elf" in tcl
    assert "RECOVERY_DDR_ECC_SCRUB_COMPLETE" in tcl
    assert "dow -force -data /tmp/Image-recovery 0x00200000" in tcl
    assert "dow -force -data /tmp/initramfs.cpio.gz 0x10000000" in tcl
    assert "dow -force -data /tmp/system-recovery.dtb 0x20000000" in tcl
    assert tcl.index('name =~ "PSU"') < tcl.index("/tmp/Image-recovery")
    assert "dow /tmp/el3-to-el2.elf" in tcl
    assert "rwr pc 0x00100000" in tcl
    assert "RECOVERY_LINUX_LAUNCHED" in tcl
    assert driver._timeouts[0] == 420


def test_load_zynqmp_recovery_linux_requires_scrub_completion(driver):
    driver.load_zynqmp_recovery_linux(
        "/tmp/psu_init.tcl",
        "/tmp/el3-to-el2.elf",
        "/tmp/Image-recovery",
        "/tmp/initramfs.cpio.gz",
        "/tmp/system-recovery.dtb",
        ddr_scrub_elf="/tmp/ddr-ecc-scrub.elf",
        ddr_scrub_done_address="0xFFFC0054",
    )
    tcl = driver._captured[0]
    assert "set scrub_done [expr {0xFFFC0054}]" in tcl
    assert "$scrub_pc != $scrub_done && $scrub_pc != ($scrub_done + 4)" in tcl
    assert "DDR ECC scrub did not reach completion loop" in tcl


def test_load_zynqmp_production_uboot_builds_verified_handoff(driver):
    driver.load_zynqmp_production_uboot(
        psu_init_tcl="/tmp/psu_init.tcl",
        pmufw_bin="/tmp/pmufw.bin",
        uboot_bin="/tmp/u-boot.bin",
        handoff_bin="/tmp/el3-to-el2.bin",
    )
    tcl = driver._captured[0]

    assert "configparams force-mem-accesses 1" in tcl
    assert "source /tmp/psu_init.tcl" in tcl
    assert "PMU ROM did not enter sleep" in tcl
    assert "dow -force -data /tmp/pmufw.bin 0xFFDC0000" in tcl
    assert "PMU firmware did not claim FW_IS_PRESENT" in tcl
    assert "mwr $pmu_control_addr [expr {$pmu_control | 0x1}]" in tcl
    assert "| 0x10" not in tcl
    assert "dow -force -data /tmp/u-boot.bin 0x08000000" in tcl
    assert "dow -force -data /tmp/el3-to-el2.bin 0x00100000" in tcl
    assert "rst -processor -clear-registers" in tcl
    assert tcl.index("rst -processor -clear-registers") < tcl.index(
        "dow -force -data /tmp/pmufw.bin"
    )
    assert tcl.rindex("rst -processor -clear-registers") < tcl.index("PMUFW_READY")
    assert "rwr pc 0x00100000" in tcl
    assert "PRODUCTION_UBOOT_LAUNCHED" in tcl


def test_load_zynqmp_production_uboot_programs_pl_and_scrubs_ddr(driver):
    driver.load_zynqmp_production_uboot(
        psu_init_tcl="/tmp/psu_init.tcl",
        pmufw_bin="/tmp/pmufw.bin",
        uboot_bin="/tmp/u-boot.bin",
        handoff_bin="/tmp/el3-to-el2.bin",
        bitstream_path="/tmp/system_top-xsdb.bin",
        ddr_scrub_elf="/tmp/ddr-ecc-scrub.elf",
    )
    tcl = driver._captured[0]

    assert "dow /tmp/ddr-ecc-scrub.elf" in tcl
    assert "DDR_ECC_SCRUB_COMPLETE" in tcl
    assert "fpga -file /tmp/system_top-xsdb.bin" in tcl
    assert "FPGA_STATE=" in tcl
    assert tcl.index("dow /tmp/ddr-ecc-scrub.elf") < tcl.index("dow -force -data /tmp/u-boot.bin")


def test_load_zynqmp_production_uboot_raises_on_xsdb_failure(driver):
    driver._run_xsdb = lambda tcl_script, timeout=300: (
        "",
        "PMU firmware did not claim FW_IS_PRESENT",
        1,
    )
    with pytest.raises(ExecutionError, match="PMU firmware did not claim FW_IS_PRESENT"):
        driver.load_zynqmp_production_uboot(
            "/tmp/psu_init.tcl",
            "/tmp/pmufw.bin",
            "/tmp/u-boot.bin",
            "/tmp/el3-to-el2.bin",
        )


def test_load_zynqmp_production_uboot_accepts_remote_hw_server(driver):
    driver.load_zynqmp_production_uboot(
        "/tmp/psu_init.tcl",
        "/tmp/pmufw.bin",
        "/tmp/u-boot.bin",
        "/tmp/el3-to-el2.bin",
        jtag_url="TCP:tron.local:3121",
    )
    assert "connect -url TCP:tron.local:3121" in driver._captured[0]


def test_load_zynqmp_production_uboot_launches_bl31_runtime(driver):
    driver.load_zynqmp_production_uboot(
        "/tmp/psu_init.tcl",
        "/tmp/pmufw.bin",
        "/tmp/u-boot.bin",
        bl31_bin="/tmp/bl31.bin",
        atf_handoff_bin="/tmp/atf-handoff.bin",
        bl31_console_uart_base="0xFF000000",
        bl31_console_ref_ctrl_address="0xFF5E0074",
    )
    tcl = driver._captured[0]
    assert "dow -force -data /tmp/bl31.bin 0xFFFEA000" in tcl
    assert "dow -force -data /tmp/atf-handoff.bin 0x00100000" in tcl
    assert "rwr r0 0x00100000" in tcl
    assert "rwr pc 0xFFFEA000" in tcl
    assert "PRODUCTION_BL31_LAUNCHED" in tcl
    assert "mwr 0xFF5E0074 0x01010F00" in tcl
    assert "$iou_rst & ~0x2" in tcl
    assert "mwr 0xFF000000 0x00000114" in tcl


def test_load_zynqmp_production_uboot_loads_pm_config_after_pmufw(driver):
    driver.load_zynqmp_production_uboot(
        "/tmp/psu_init.tcl",
        "/tmp/pmufw.bin",
        "/tmp/u-boot.bin",
        handoff_bin="/tmp/el3-to-el2.bin",
        pm_config_bin="/tmp/pm-config.bin",
    )
    tcl = driver._captured[0]
    assert "dow -force -data /tmp/pm-config.bin 0x00200000" in tcl
    assert tcl.index("PMUFW_READY") < tcl.index("/tmp/pm-config.bin")
    assert tcl.index("/tmp/pm-config.bin") < tcl.index("/tmp/u-boot.bin")


def test_load_zynqmp_production_uboot_rejects_partial_bl31_inputs(driver):
    with pytest.raises(ExecutionError, match="must be supplied together"):
        driver.load_zynqmp_production_uboot(
            "/tmp/psu_init.tcl",
            "/tmp/pmufw.bin",
            "/tmp/u-boot.bin",
            bl31_bin="/tmp/bl31.bin",
        )
