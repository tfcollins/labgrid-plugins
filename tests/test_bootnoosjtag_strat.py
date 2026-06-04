"""Unit tests for the BootNoOSJTAG strategy (no-os firmware flash)."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootnoosjtag import BootNoOSJTAG, Status


def _make_strategy(**overrides):
    """Construct a BootNoOSJTAG bypassing labgrid binding machinery.

    Pass config as kwargs (firmware_elf, bitstream_path, …); bindings
    (power/jtag/shell) default to MagicMock and can be overridden.
    """
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    cfg = {
        "firmware_elf": "/tmp/fw.elf",
        "boot_marker": "Running IIOD server",
        "boot_timeout": 30,
        "power_settle_time": 0,
    }
    cfg.update({k: v for k, v in overrides.items() if k not in ("power", "jtag", "shell")})
    s = BootNoOSJTAG(target, "bootnoosjtag", **cfg)

    s.power = overrides.get("power", MagicMock())
    s.jtag = overrides.get("jtag", MagicMock())
    s.shell = overrides.get("shell", MagicMock())
    return s


def test_unknown_rejected():
    s = _make_strategy()
    with pytest.raises(StrategyError):
        s.transition(Status.unknown)


def test_skip_same_status():
    s = _make_strategy()
    s.status = Status.shell
    s.transition(Status.shell)
    s.jtag.load_and_run_elf.assert_not_called()
    s.power.on.assert_not_called()


def test_powered_off_calls_power_off():
    s = _make_strategy()
    s.transition(Status.powered_off)
    s.power.off.assert_called_once()
    s.target.deactivate.assert_any_call(s.shell)
    assert s.status == Status.powered_off


def test_powered_on_cycles_power():
    s = _make_strategy()  # default status=unknown -> full off+on cycle
    s.transition(Status.powered_on)
    assert s.power.off.called
    assert s.power.on.called
    assert s.status == Status.powered_on


def test_powered_on_from_off_only_powers_on():
    # already powered off -> don't redundantly re-power-off, just power on.
    s = _make_strategy()
    s.status = Status.powered_off
    s.transition(Status.powered_on)
    s.power.off.assert_not_called()
    assert s.power.on.called


def test_shell_flashes_elf_and_validates_banner():
    s = _make_strategy(bitstream_path="/tmp/sys.bit", ps7_init_tcl="/tmp/ps7.tcl")
    s.transition(Status.shell)

    s.jtag.load_and_run_elf.assert_called_once_with(
        elf_path="/tmp/fw.elf",
        a9_target_name="*Cortex-A9 MPCore #0",
        bitstream_path="/tmp/sys.bit",
        ps7_init_tcl="/tmp/ps7.tcl",
    )
    # no-os has no login prompt — the console is only read for the banner.
    assert s.shell.bypass_login is True
    s.shell.console.expect.assert_called_once()
    args, kwargs = s.shell.console.expect.call_args
    assert "Running IIOD server" in (list(args) + list(kwargs.values()))
    assert s.status == Status.shell


def test_shell_requires_firmware_elf():
    s = _make_strategy(firmware_elf=None)
    with pytest.raises(StrategyError, match="firmware_elf"):
        s.transition(Status.shell)
