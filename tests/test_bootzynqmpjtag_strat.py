"""Unit tests for the BootZynqMPJTAG strategy."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootzynqmpjtag import BootZynqMPJTAG, Status


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Bypass real sleeps so tests run fast."""
    monkeypatch.setattr(
        "adi_lg_plugins.strategies.bootzynqmpjtag.time.sleep", lambda *_a, **_kw: None
    )


def _make_strategy(**overrides):
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    s = BootZynqMPJTAG(
        target,
        "boot_zynqmp",
        psu_init_tcl="/tmp/psu_init.tcl",
        spl_elf="/tmp/u-boot-spl",
    )
    s.power = MagicMock()
    s.jtag = MagicMock()
    s.shell = MagicMock()
    s.shell.prompt = "# "
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _production_strategy(**overrides):
    values = {
        "pmufw_bin": "/tmp/pmufw.bin",
        "uboot_bin": "/tmp/u-boot.bin",
        "handoff_bin": "/tmp/el3-to-el2.bin",
    }
    values.update(overrides)
    return _make_strategy(**values)


def test_jtag_bootstrap_invokes_load_zynqmp_uboot():
    s = _make_strategy()
    s.transition("jtag_bootstrap")
    s.jtag.load_zynqmp_uboot.assert_called_once()
    kwargs = s.jtag.load_zynqmp_uboot.call_args.kwargs
    assert kwargs["psu_init_tcl"] == "/tmp/psu_init.tcl"
    assert kwargs["spl_elf"] == "/tmp/u-boot-spl"
    assert s.status == Status.jtag_bootstrap


def test_jtag_bootstrap_passes_bitstream_and_tuning():
    s = _make_strategy(
        bitstream_path="/tmp/system_top.bit",
        apu_release_rst_value="0x0",
        dcc_log_path="/tmp/dcc.log",
        a53_target_name="*Cortex-A53*#1*",
    )
    s.transition("jtag_bootstrap")
    kwargs = s.jtag.load_zynqmp_uboot.call_args.kwargs
    assert kwargs["bitstream_path"] == "/tmp/system_top.bit"
    assert kwargs["apu_release_rst_value"] == "0x0"
    assert kwargs["dcc_log_path"] == "/tmp/dcc.log"
    assert kwargs["a53_target_name"] == "*Cortex-A53*#1*"


def test_powered_on_cycles_power():
    s = _make_strategy()
    s.transition("powered_on")
    s.power.off.assert_called_once()
    s.power.on.assert_called_once()
    assert s.status == Status.powered_on


def test_transition_unknown_raises():
    s = _make_strategy()
    with pytest.raises(StrategyError):
        s.transition("unknown")


def test_jtag_bootstrap_requires_psu_init_tcl():
    s = _make_strategy(psu_init_tcl=None)
    with pytest.raises(StrategyError) as excinfo:
        s.transition("jtag_bootstrap")
    # @never_retry wraps the original error; the cause carries the detail.
    assert "psu_init_tcl" in str(excinfo.value.__cause__)


def test_jtag_bootstrap_requires_spl_elf():
    s = _make_strategy(spl_elf=None)
    with pytest.raises(StrategyError) as excinfo:
        s.transition("jtag_bootstrap")
    assert "spl_elf" in str(excinfo.value.__cause__)


def test_transition_accepts_enum():
    s = _make_strategy()
    s.transition(Status.powered_off)
    s.power.off.assert_called_once()
    assert s.status == Status.powered_off


def test_shell_deactivated_on_power_off():
    s = _make_strategy()
    s.transition("powered_off")
    s.target.deactivate.assert_any_call(s.shell)


def test_optional_shell_none_is_ok():
    s = _make_strategy(shell=None)
    s.transition("powered_off")
    # No shell to deactivate; power path still runs.
    s.power.off.assert_called_once()
    assert s.status == Status.powered_off


def test_production_boot_invokes_verified_handoff():
    s = _production_strategy(
        bitstream_path="/tmp/system_top-xsdb.bin",
        ddr_scrub_elf="/tmp/ddr-ecc-scrub.elf",
        jtag_url="TCP:tron.local:3121",
    )
    s.transition("production_boot")

    s.jtag.load_zynqmp_production_uboot.assert_called_once()
    kwargs = s.jtag.load_zynqmp_production_uboot.call_args.kwargs
    assert kwargs["pmufw_bin"] == "/tmp/pmufw.bin"
    assert kwargs["uboot_bin"] == "/tmp/u-boot.bin"
    assert kwargs["handoff_bin"] == "/tmp/el3-to-el2.bin"
    assert kwargs["ddr_scrub_elf"] == "/tmp/ddr-ecc-scrub.elf"
    assert kwargs["bitstream_path"] == "/tmp/system_top-xsdb.bin"
    assert kwargs["jtag_url"] == "TCP:tron.local:3121"
    assert s.status == Status.production_boot


@pytest.mark.parametrize("missing", ["psu_init_tcl", "pmufw_bin", "uboot_bin", "handoff_bin"])
def test_production_boot_requires_all_inputs(missing):
    s = _production_strategy()
    setattr(s, missing, None)
    with pytest.raises(StrategyError) as excinfo:
        s.transition("production_boot")
    assert missing in str(excinfo.value.__cause__)


def test_production_boot_passes_bl31_runtime_pair():
    s = _production_strategy(
        handoff_bin=None,
        bl31_bin="/tmp/bl31.bin",
        atf_handoff_bin="/tmp/atf-handoff.bin",
    )
    s.transition("production_boot")
    kwargs = s.jtag.load_zynqmp_production_uboot.call_args.kwargs
    assert kwargs["handoff_bin"] is None
    assert kwargs["bl31_bin"] == "/tmp/bl31.bin"
    assert kwargs["atf_handoff_bin"] == "/tmp/atf-handoff.bin"


def test_production_boot_rejects_partial_bl31_pair():
    s = _production_strategy(bl31_bin="/tmp/bl31.bin")
    with pytest.raises(StrategyError) as excinfo:
        s.transition("production_boot")
    assert "must be set together" in str(excinfo.value.__cause__)


def test_recovery_linux_loads_direct_jtag_payloads_and_checks_marker():
    s = _make_strategy(
        recovery_trampoline_elf="/tmp/el3-to-el2.elf",
        recovery_kernel_image="/tmp/Image-recovery",
        recovery_initramfs="/tmp/initramfs.cpio.gz",
        recovery_dtb="/tmp/system-recovery.dtb",
        ddr_scrub_elf="/tmp/ddr-ecc-scrub.elf",
        recovery_ddr_scrub_elf="/tmp/ddr-ecc-scrub-low.elf",
        recovery_ddr_scrub_done_address="0xFFFC002C",
        recovery_bitstream_path="/tmp/system_top.bit",
        recovery_post_init_mask_writes=[("0xFF5E0238", "0x2", "0x0")],
        serial_host_override="exporter.local",
        serial_protocol_override="raw",
    )
    s.transition("recovery_linux")
    kwargs = s.jtag.load_zynqmp_recovery_linux.call_args.kwargs
    assert kwargs["kernel_image"] == "/tmp/Image-recovery"
    assert kwargs["initramfs"] == "/tmp/initramfs.cpio.gz"
    assert kwargs["dtb"] == "/tmp/system-recovery.dtb"
    assert kwargs["ddr_scrub_elf"] == "/tmp/ddr-ecc-scrub-low.elf"
    assert kwargs["ddr_scrub_done_address"] == "0xFFFC002C"
    assert kwargs["ddr_scrub_settle_ms"] == 30000
    assert kwargs["bitstream_path"] == "/tmp/system_top.bit"
    assert kwargs["post_init_mask_writes"] == [("0xFF5E0238", "0x2", "0x0")]
    assert s.shell.bypass_login is True
    assert s.shell.console.port.host == "exporter.local"
    assert s.shell.console.port.protocol == "raw"
    s.shell.console.expect.assert_any_call("RECOVERY_READY", timeout=s.recovery_timeout)
    s.shell._inject_run.assert_called_once()
    assert s.status == Status.recovery_linux


def test_sd_flash_done_streams_syncs_and_runs_post_flash_commands():
    s = _make_strategy(
        recovery_trampoline_elf="/tmp/el3-to-el2.elf",
        recovery_kernel_image="/tmp/Image-recovery",
        recovery_initramfs="/tmp/initramfs.cpio.gz",
        recovery_dtb="/tmp/system-recovery.dtb",
        sd_image_url="http://10.0.0.71:8000/kuiper.img",
        sd_image_size=10305404928,
        sd_head_sha256="headhash",
        sd_tail_sha256="tailhash",
        post_flash_commands=["mount /dev/mmcblk0p1 /mnt && cp /mnt/board/BOOT.BIN /mnt/BOOT.BIN"],
    )
    s.status = Status.recovery_linux
    s.shell.run.side_effect = [(["SD_FLASH_OK"], [], 0), ([], [], 0)]
    s.transition("sd_flash_done")
    flash = s.shell.run.call_args_list[0].args[0]
    assert "set -o pipefail" in flash
    assert 'dd of="/dev/mmcblk0" bs=4M conv=fsync' in flash
    assert "blockdev --rereadpt /dev/mmcblk0" in flash
    assert 'test "$head" = "headhash"' in flash
    assert 'test "$tail" = "tailhash"' in flash
    assert "SD_FLASH_OK" in flash
    assert s.shell.run.call_args_list[1].args[0].startswith("mount ")
    assert s.status == Status.sd_flash_done


def test_production_uboot_prompt_is_target_verified():
    s = _production_strategy()
    s.shell.console.expect.return_value = 0
    s.transition("production_uboot_prompt")
    assert s.jtag.load_zynqmp_production_uboot.called
    assert s.shell.bypass_login is True
    s.shell.console.expect.assert_any_call(s.production_uboot_prompt, timeout=0.1)
    assert s.status == Status.production_uboot_prompt


def test_kuiper_shell_runs_explicit_sd_boot_and_runtime_checks():
    s = _production_strategy(
        kuiper_verify_commands=["ip link show eth0", "test -e /sys/bus/iio/devices/iio:device0"],
    )
    s.status = Status.production_uboot_prompt
    s.shell.console.expect.return_value = 0
    s.transition("kuiper_shell")
    s.shell.console.sendline.assert_any_call("setenv partid 1; run sdboot")
    s.shell.console.expect.assert_any_call("Starting kernel", timeout=s.kuiper_boot_timeout)
    s.shell.console.expect.assert_any_call(s.kuiper_shell_marker, timeout=s.kuiper_boot_timeout)
    s.shell._inject_run.assert_called_once()
    s.shell.run_check.assert_any_call("ip link show eth0", timeout=s.kuiper_verify_timeout)
    assert s.status == Status.kuiper_shell


def test_transition_shell_aliases_kuiper_shell():
    """The generic hardware-request flow transitions to "shell"; for this
    strategy that must mean kuiper_shell (not a KeyError on Status["shell"]).
    Both spellings hit the same missing-production-inputs validation."""
    with pytest.raises(StrategyError):
        _make_strategy().transition("kuiper_shell")
    with pytest.raises(StrategyError):
        _make_strategy().transition("shell")
