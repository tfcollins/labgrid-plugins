"""Unit tests for BootTickFPGASSH: Tick deploy ordering and delegation."""

import logging
from unittest import mock

from adi_lg_plugins.strategies.bootfpgasocssh import BootFPGASoCSSH
from adi_lg_plugins.strategies.bootfpgasocssh import Status as ParentStatus
from adi_lg_plugins.strategies.boottickfpgassh import BootTickFPGASSH, Status


def _strategy():
    s = BootTickFPGASSH.__new__(BootTickFPGASSH)
    s.status = Status.unknown
    s.target = mock.MagicMock()
    s.logger = logging.getLogger("test_boottick")
    s.tick_fpga = mock.MagicMock()
    s.tick_overlay = mock.MagicMock()
    s.tick_module = mock.MagicMock()
    s.power = mock.MagicMock()
    return s


def test_module_loaded_runs_full_deploy_in_order():
    s = _strategy()
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._transition_tick(Status.tick_module_loaded)

    parent.assert_any_call("shell")  # booted to a shell before deploy
    s.tick_fpga.load_bitstream.assert_called_once()
    s.tick_overlay.apply.assert_called_once()
    s.tick_module.load.assert_called_once()
    assert s.status == Status.tick_module_loaded


def test_tick_off_reverses_then_powers_off():
    s = _strategy()
    s._transition_tick(Status.tick_off)
    s.tick_module.unload.assert_called_once()
    s.tick_overlay.remove.assert_called_once()
    s.power.off.assert_called_once()


def test_dispatch_delegates_unknown_states_to_parent():
    s = _strategy()
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._dispatch("shell")  # not a Tick Status -> parent handles it
    parent.assert_called_once_with("shell")


def test_dispatch_delegates_parent_enum_member_to_parent():
    # The parent's internal recursion re-enters the child with a PARENT Status member;
    # it must delegate, not crash. This guards the Status[...] KeyError linchpin.
    s = _strategy()
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._dispatch(ParentStatus.shell)
    parent.assert_called_once_with(ParentStatus.shell)


def test_repeat_module_loaded_is_noop():
    s = _strategy()
    s.status = Status.tick_module_loaded
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._transition_tick(Status.tick_module_loaded)
    parent.assert_not_called()
    s.tick_module.load.assert_not_called()


def test_tick_off_without_power_binding():
    s = _strategy()
    s.power = None
    s._transition_tick(Status.tick_off)
    s.tick_module.unload.assert_called_once()
    s.tick_overlay.remove.assert_called_once()
    assert s.status == Status.tick_off
