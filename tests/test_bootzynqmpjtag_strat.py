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
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


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
