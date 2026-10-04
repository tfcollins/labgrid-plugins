"""Unit tests for the explicit openFPGALoader strategy."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootopenfpgaloader import BootOpenFPGALoader, Status


def _strategy(**overrides):
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind
    cfg = {
        "bitstream_path": "/tmp/design.bit",
        "boot_marker": "READY",
        "boot_timeout": 15,
        "power_settle_time": 0,
    }
    cfg.update(
        {
            key: value
            for key, value in overrides.items()
            if key not in ("power", "programmer", "shell")
        }
    )
    strategy = BootOpenFPGALoader(target, "bootopenfpgaloader", **cfg)
    strategy.power = overrides.get("power", MagicMock())
    strategy.programmer = overrides.get("programmer", MagicMock())
    strategy.shell = overrides.get("shell", MagicMock())
    return strategy


def test_unknown_rejected():
    with pytest.raises(StrategyError):
        _strategy().transition(Status.unknown)


def test_powered_on_cycles_power():
    strategy = _strategy()
    strategy.transition(Status.powered_on)
    strategy.power.off.assert_called_once()
    strategy.power.on.assert_called_once()
    assert strategy.status == Status.powered_on


def test_programmed_only_claims_programming():
    strategy = _strategy()
    strategy.transition(Status.programmed)
    strategy.programmer.load.assert_called_once_with("/tmp/design.bit")
    strategy.shell.console.expect.assert_not_called()
    assert strategy.status == Status.programmed


def test_programmed_requires_bitstream():
    strategy = _strategy(bitstream_path=None)
    with pytest.raises(StrategyError, match="bitstream_path"):
        strategy.transition(Status.programmed)
    assert strategy.status != Status.programmed


def test_shell_requires_target_visible_marker():
    strategy = _strategy()
    strategy.transition(Status.shell)
    strategy.programmer.load.assert_called_once_with("/tmp/design.bit")
    strategy.shell.console.expect.assert_called_once_with("READY", timeout=15)
    assert strategy.shell.bypass_login is True
    assert strategy.status == Status.shell


def test_shell_does_not_claim_success_after_marker_failure():
    strategy = _strategy()
    strategy.shell.console.expect.side_effect = TimeoutError("no marker")
    with pytest.raises(TimeoutError, match="no marker"):
        strategy.transition(Status.shell)
    assert strategy.status == Status.programmed


def test_shell_requires_marker():
    strategy = _strategy(boot_marker=None)
    with pytest.raises(StrategyError, match="boot_marker"):
        strategy.transition(Status.shell)
    assert strategy.status == Status.programmed


def test_shell_requires_bound_shell_driver():
    strategy = _strategy(shell=None)
    with pytest.raises(StrategyError, match="shell driver"):
        strategy.transition(Status.shell)
    assert strategy.status == Status.programmed
