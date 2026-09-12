"""Exporter payload staging and Tcl path safety for XilinxJTAGDriver."""

import inspect
import logging
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState

from adi_lg_plugins.drivers.xilinxjtagdriver import XilinxJTAGDriver, _tcl_quote_path

FILE_PARAMETERS = {
    "load_zynq_uboot": {"ps7_init_tcl", "uboot_elf", "bitstream_path", "fsbl_elf"},
    "load_and_run_elf": {"elf_path", "bitstream_path", "ps7_init_tcl"},
    "load_zynqmp_uboot": {"psu_init_tcl", "spl_elf", "bitstream_path"},
    "load_zynqmp_production_uboot": {
        "psu_init_tcl",
        "pmufw_bin",
        "uboot_bin",
        "handoff_bin",
        "bitstream_path",
        "ddr_scrub_elf",
        "bl31_bin",
        "atf_handoff_bin",
        "pm_config_bin",
    },
    "load_zynqmp_recovery_linux": {
        "psu_init_tcl",
        "trampoline_elf",
        "kernel_image",
        "initramfs",
        "dtb",
        "ddr_scrub_elf",
        "bitstream_path",
    },
}
RESOURCE_FILE_METHODS = {
    "flash_bitstream": {"bitstream_path"},
    "download_kernel": {"kernel_path"},
    "load_bitstream_and_kernel_and_start": {"bitstream_path", "kernel_path"},
}


@pytest.fixture
def driver():
    d = XilinxJTAGDriver.__new__(XilinxJTAGDriver)
    d.target = MagicMock()
    d.target.resources = []
    d.name = "jtag"
    d.logger = logging.getLogger("test_xilinx_jtag_exporter")
    d.xilinxvivado = MagicMock(xsdb_path="xsdb")
    d.xilinxdevicejtag = MagicMock(
        bitstream_path="client/resource system.bit",
        kernel_path="client/resource kernel.elf",
        root_target=1,
        microblaze_target=3,
    )
    d.state = BindingState.active
    d.staged = []
    d.scripts = []

    def stage(path):
        d.staged.append(path)
        return f"/exporter/staged/{Path(path).name}"

    def run(tcl_script, timeout=300):
        d.scripts.append(tcl_script)
        return "", "", 0

    d._stage_file = stage
    d._run_xsdb = run
    return d


def test_file_parameter_inventory_matches_public_api():
    """Keep an explicit review gate for every public file-bearing argument."""
    public_parameters = {
        name: set(inspect.signature(getattr(XilinxJTAGDriver, name)).parameters) - {"self"}
        for name in FILE_PARAMETERS
    }
    for method, file_parameters in FILE_PARAMETERS.items():
        assert file_parameters <= public_parameters[method]

    discovered = {}
    for name, value in XilinxJTAGDriver.__dict__.items():
        if name.startswith("_") or not inspect.isfunction(value):
            continue
        parameters = set(inspect.signature(value).parameters) - {"self", "dcc_log_path"}
        file_parameters = {
            parameter
            for parameter in parameters
            if parameter.endswith(("_path", "_tcl", "_elf", "_bin", "_image"))
            or parameter in {"initramfs", "dtb"}
        }
        if file_parameters:
            discovered[name] = file_parameters
    assert discovered == FILE_PARAMETERS

    assert set(RESOURCE_FILE_METHODS) <= {
        name
        for name, value in inspect.getmembers(XilinxJTAGDriver, inspect.isfunction)
        if not name.startswith("_")
    }


@pytest.mark.parametrize(
    ("method", "kwargs", "expected"),
    [
        (
            "load_zynq_uboot",
            {
                "ps7_init_tcl": "client/ps7 init.tcl",
                "uboot_elf": "client/u boot.elf",
                "bitstream_path": "client/system top.bit",
                "fsbl_elf": "client/fsbl.elf",
            },
            FILE_PARAMETERS["load_zynq_uboot"],
        ),
        (
            "load_and_run_elf",
            {
                "elf_path": "client/fw.elf",
                "bitstream_path": "client/system top.bit",
                "ps7_init_tcl": "client/ps7 init.tcl",
            },
            FILE_PARAMETERS["load_and_run_elf"],
        ),
        (
            "load_zynqmp_uboot",
            {
                "psu_init_tcl": "client/psu init.tcl",
                "spl_elf": "client/u-boot-spl",
                "bitstream_path": "client/system top.bit",
            },
            FILE_PARAMETERS["load_zynqmp_uboot"],
        ),
        (
            "load_zynqmp_production_uboot",
            {
                "psu_init_tcl": "client/psu init.tcl",
                "pmufw_bin": "client/pmufw.bin",
                "uboot_bin": "client/u boot.bin",
                "bitstream_path": "client/system top.bit",
                "ddr_scrub_elf": "client/ddr scrub.elf",
                "bl31_bin": "client/bl31.bin",
                "atf_handoff_bin": "client/atf handoff.bin",
                "pm_config_bin": "client/pm config.bin",
            },
            FILE_PARAMETERS["load_zynqmp_production_uboot"] - {"handoff_bin"},
        ),
        (
            "load_zynqmp_production_uboot",
            {
                "psu_init_tcl": "client/psu init.tcl",
                "pmufw_bin": "client/pmufw.bin",
                "uboot_bin": "client/u boot.bin",
                "handoff_bin": "client/el3 handoff.bin",
            },
            {"psu_init_tcl", "pmufw_bin", "uboot_bin", "handoff_bin"},
        ),
        (
            "load_zynqmp_recovery_linux",
            {
                "psu_init_tcl": "client/psu init.tcl",
                "trampoline_elf": "client/el3 trampoline.elf",
                "kernel_image": "client/Image recovery",
                "initramfs": "client/initramfs.cpio.gz",
                "dtb": "client/system recovery.dtb",
                "ddr_scrub_elf": "client/ddr scrub.elf",
                "bitstream_path": "client/system top.bit",
            },
            FILE_PARAMETERS["load_zynqmp_recovery_linux"],
        ),
    ],
)
def test_public_method_payloads_are_staged_and_rewritten(driver, method, kwargs, expected):
    getattr(driver, method)(**kwargs)

    expected_sources = {os.path.abspath(kwargs[name]) for name in expected}
    assert set(driver.staged) == expected_sources
    tcl = driver.scripts[-1]
    for name in expected:
        source = os.path.abspath(kwargs[name])
        staged = f"/exporter/staged/{Path(source).name}"
        assert source not in tcl
        assert _tcl_quote_path(staged) in tcl


@pytest.mark.parametrize(("method", "resource_names"), RESOURCE_FILE_METHODS.items())
def test_resource_payloads_are_staged_and_rewritten(driver, method, resource_names):
    getattr(driver, method)()

    expected_sources = {
        os.path.abspath(getattr(driver.xilinxdevicejtag, name)) for name in resource_names
    }
    assert set(driver.staged) == expected_sources
    tcl = driver.scripts[-1]
    for source in expected_sources:
        assert source not in tcl
        assert _tcl_quote_path(f"/exporter/staged/{Path(source).name}") in tcl


def test_explicit_exporter_path_marker_bypasses_staging(driver):
    driver.load_and_run_elf(
        "exporter:/srv/jtag/fw.elf",
        bitstream_path="exporter:/srv/jtag/system.bit",
        ps7_init_tcl="exporter:/srv/jtag/ps7_init.tcl",
    )

    assert driver.staged == []
    tcl = driver.scripts[-1]
    assert "exporter:" not in tcl
    assert "/srv/jtag/fw.elf" in tcl
    assert "/srv/jtag/system.bit" in tcl
    assert "/srv/jtag/ps7_init.tcl" in tcl


def test_resource_exporter_path_marker_bypasses_staging(driver):
    driver.xilinxdevicejtag.bitstream_path = "exporter:/srv/jtag/system.bit"
    driver.xilinxdevicejtag.kernel_path = "exporter:/srv/jtag/kernel.elf"

    driver.load_bitstream_and_kernel_and_start()

    assert driver.staged == []
    assert "exporter:" not in driver.scripts[-1]
    assert "fpga -f /srv/jtag/system.bit" in driver.scripts[-1]
    assert "dow /srv/jtag/kernel.elf" in driver.scripts[-1]


def test_empty_exporter_path_marker_is_rejected(driver):
    with pytest.raises(ValueError, match="must not be empty"):
        driver.load_and_run_elf("exporter:")


@pytest.mark.parametrize(
    "path",
    [
        '/tmp/space and $dollar [exec touch /tmp/bad]; quote".elf',
        "/tmp/braces {and} backslash\\payload.bit",
        "/tmp/unicode-雪-文件.tcl",
    ],
)
def test_tcl_path_quote_round_trips_without_substitution(path):
    quoted = _tcl_quote_path(path)
    result = subprocess.run(
        ["tclsh"],
        input=f"set value {quoted}\nputs -nonewline $value\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout == path


def test_dcc_output_path_is_exporter_side_and_safely_quoted(driver):
    output = "/exporter/logs/dcc $run;[exit 9].log"
    driver.load_zynqmp_uboot(
        "exporter:/srv/psu_init.tcl",
        "exporter:/srv/u-boot-spl",
        dcc_log_path=output,
    )

    assert driver.staged == []
    assert f"open {_tcl_quote_path(output)} w" in driver.scripts[-1]
