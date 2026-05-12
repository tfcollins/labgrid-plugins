"""Unit tests for the BootZynq7000JTAGRecovery strategy."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootzynq7000recovery import (
    BootZynq7000JTAGRecovery,
    Status,
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Bypass real sleeps in the strategy so tests run fast."""
    monkeypatch.setattr(
        "adi_lg_plugins.strategies.bootzynq7000recovery.time.sleep", lambda *_a, **_kw: None
    )


def _make_strategy(**overrides):
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    s = BootZynq7000JTAGRecovery(
        target,
        "boot_recovery",
        ps7_init_tcl="/tmp/ps7_init.tcl",
        uboot_elf="/tmp/u-boot.elf",
        recovery_kernel="zImage.recovery",
        recovery_dtb="zynq-zc706.recovery.dtb",
        recovery_initramfs="uInitrd.recovery",
        sd_image_url="http://host:8080/zc706-kuiper.img",
    )

    s.power = MagicMock()
    s.jtag = MagicMock()
    s.shell = MagicMock()
    s.shell.prompt = "# "
    s.tftp_server = MagicMock()
    s.tftp_server.get_ip.return_value = "10.0.0.1"
    s.tftp_driver = MagicMock()
    s.tftp_driver.resource.port = 3069
    s.tftp_driver.resource.root = "/tmp/tftp"
    s.ssh = None

    for k, v in overrides.items():
        setattr(s, k, v)
    return s


# ---------- transition guardrails -----------------------------------------


def test_unknown_rejected():
    s = _make_strategy()
    # @never_retry wraps the raised StrategyError into "is in broken state".
    with pytest.raises(StrategyError, match="broken state"):
        s.transition(Status.unknown)


def test_skip_same_status():
    s = _make_strategy()
    s.status = Status.powered_off
    s.transition(Status.powered_off)
    # No power calls because we short-circuited.
    s.power.off.assert_not_called()


# ---------- per-state behavior --------------------------------------------


def test_powered_off_calls_power_off():
    s = _make_strategy()
    s.transition(Status.powered_off)
    s.power.off.assert_called_once()
    s.target.deactivate.assert_any_call(s.shell)
    s.target.deactivate.assert_any_call(s.tftp_driver)
    assert s.status == Status.powered_off


def test_powered_on_cold_cycles():
    s = _make_strategy()
    s.status = Status.powered_off
    s.transition(Status.powered_on)
    # off → on order via cold-cycle
    assert s.power.off.called
    assert s.power.on.called
    assert s.status == Status.powered_on


def test_jtag_bootstrap_invokes_load_zynq_uboot():
    s = _make_strategy()
    s.status = Status.powered_on
    s.transition(Status.jtag_bootstrap)

    s.jtag.load_zynq_uboot.assert_called_once_with(
        ps7_init_tcl="/tmp/ps7_init.tcl",
        uboot_elf="/tmp/u-boot.elf",
        a9_target_name="*Cortex-A9 MPCore #0",
        bitstream_path=None,
        fsbl_elf=None,
    )
    assert s.status == Status.jtag_bootstrap


def test_jtag_bootstrap_retries_on_failure_then_succeeds():
    s = _make_strategy(jtag_bootstrap_retries=2)
    s.status = Status.powered_on
    # Fail once, succeed on retry.
    s.jtag.load_zynq_uboot.side_effect = [RuntimeError("xsdb timeout"), None]
    s.transition(Status.jtag_bootstrap)
    assert s.jtag.load_zynq_uboot.call_count == 2
    # One cold-cycle happens between attempts.
    assert s.power.off.call_count == 1
    assert s.power.on.call_count == 1
    assert s.status == Status.jtag_bootstrap


def test_jtag_bootstrap_exhausts_retries():
    s = _make_strategy(jtag_bootstrap_retries=1)
    s.status = Status.powered_on
    s.jtag.load_zynq_uboot.side_effect = RuntimeError("xsdb timeout")
    # @never_retry wraps the underlying StrategyError; verify the cause.
    with pytest.raises(StrategyError, match="broken state") as exc:
        s.transition(Status.jtag_bootstrap)
    assert "exhausted retries" in str(exc.value.__cause__)


def test_jtag_bootstrap_missing_ps7_init_tcl_errors():
    s = _make_strategy()
    s.status = Status.powered_on
    s.ps7_init_tcl = None
    with pytest.raises(StrategyError, match="broken state") as exc:
        s.transition(Status.jtag_bootstrap)
    assert "ps7_init_tcl" in str(exc.value.__cause__)


def test_uboot_prompt_stops_autoboot_and_checks_prompt():
    s = _make_strategy()
    s.status = Status.jtag_bootstrap
    s.transition(Status.uboot_prompt)

    s.shell.console.expect.assert_any_call(
        "Hit any key to stop autoboot", timeout=s.wait_for_uboot_prompt_timeout
    )
    # Space was sent to stop autoboot.
    sent = [c.args[0] for c in s.shell.console.sendline.call_args_list]
    assert " " in sent
    s.shell._check_prompt_uboot.assert_called()
    assert s.status == Status.uboot_prompt


def test_tftp_recovery_kernel_issues_full_command_sequence():
    s = _make_strategy()
    s.status = Status.uboot_prompt
    s.transition(Status.tftp_recovery_kernel)

    issued = [call.args[0] for call in s.shell.run_uboot.call_args_list]
    joined = " ".join(issued)
    assert "setenv autoload no" in joined
    assert "dhcp" in joined
    assert "setenv serverip 10.0.0.1" in joined
    assert "setenv tftpdstport 3069" in joined
    assert f"setenv bootargs {s.bootargs}" in joined
    assert f"tftpboot {s.kernel_addr} zImage.recovery" in joined
    assert f"tftpboot {s.dtb_addr} zynq-zc706.recovery.dtb" in joined
    assert f"tftpboot {s.initramfs_addr} uInitrd.recovery" in joined

    # bootm sent via raw sendline (no run_uboot — it never returns to prompt).
    sendline_args = [c.args[0] for c in s.shell.console.sendline.call_args_list]
    bootm_line = f"bootm {s.kernel_addr} {s.initramfs_addr} {s.dtb_addr}"
    assert bootm_line in sendline_args


def test_tftp_recovery_kernel_missing_initramfs_errors():
    s = _make_strategy()
    s.status = Status.uboot_prompt
    s.recovery_initramfs = None
    with pytest.raises(StrategyError, match="broken state") as exc:
        s.transition(Status.tftp_recovery_kernel)
    assert "recovery_initramfs" in str(exc.value.__cause__)


def test_linux_recovery_expects_login_marker():
    s = _make_strategy()
    s.status = Status.tftp_recovery_kernel
    s.transition(Status.linux_recovery)

    s.shell.console.expect.assert_any_call(
        s.recovery_login_marker, timeout=s.wait_for_recovery_linux_timeout
    )
    # bypass_login must be cleared so login prompt is honored.
    assert s.shell.bypass_login is False
    assert s.status == Status.linux_recovery


def test_sd_flash_done_runs_download_dd_command():
    s = _make_strategy()
    s.status = Status.linux_recovery
    s.shell.run.return_value = (["SD_FLASH_OK"], [], 0)

    s.transition(Status.sd_flash_done)

    s.shell.run.assert_called_once()
    cmd = s.shell.run.call_args.args[0]
    # Default download command is wget (busybox-friendly); override via
    # download_cmd_template if your recovery rootfs has curl instead.
    assert "wget" in cmd
    assert s.sd_image_url in cmd
    assert f'dd of="{s.sd_device}"' in cmd
    assert "sync" in cmd
    assert "SD_FLASH_OK" in cmd
    assert s.status == Status.sd_flash_done


def test_sd_flash_done_honors_download_cmd_template():
    s = _make_strategy()
    s.download_cmd_template = 'curl -fsSL --retry 3 "{url}"'
    s.status = Status.linux_recovery
    s.shell.run.return_value = (["SD_FLASH_OK"], [], 0)

    s.transition(Status.sd_flash_done)

    cmd = s.shell.run.call_args.args[0]
    assert 'curl -fsSL --retry 3 "' + s.sd_image_url + '"' in cmd


def test_sd_flash_done_fails_on_nonzero_exit():
    s = _make_strategy()
    s.status = Status.linux_recovery
    s.shell.run.return_value = ([], ["disk full"], 1)

    with pytest.raises(StrategyError, match="broken state") as exc:
        s.transition(Status.sd_flash_done)
    assert "SD flash failed" in str(exc.value.__cause__)


def test_sd_flash_done_fails_when_marker_missing():
    s = _make_strategy()
    s.status = Status.linux_recovery
    # exit 0 but no SD_FLASH_OK marker → still treated as failure.
    s.shell.run.return_value = (["something else"], [], 0)

    with pytest.raises(StrategyError, match="broken state") as exc:
        s.transition(Status.sd_flash_done)
    assert "SD flash failed" in str(exc.value.__cause__)
