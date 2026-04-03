from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootrpi import BootRPI, Status


@pytest.fixture
def mock_target():
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind
    return target


@pytest.fixture
def strategy_all_drivers(mock_target):
    """Strategy with all optional drivers available."""
    strategy = BootRPI(mock_target, "rpi_strat")
    strategy.ssh = MagicMock()
    strategy.power = MagicMock()
    strategy.shell = MagicMock()
    strategy.sdmux = MagicMock()
    return strategy


@pytest.fixture
def strategy_ssh_only(mock_target):
    """Strategy with only SSH (no optional drivers)."""
    strategy = BootRPI(mock_target, "rpi_strat")
    strategy.ssh = MagicMock()
    strategy.power = None
    strategy.shell = None
    strategy.sdmux = None
    return strategy


@pytest.fixture
def strategy_ssh_shell(mock_target):
    """Strategy with SSH and serial console."""
    strategy = BootRPI(mock_target, "rpi_strat")
    strategy.ssh = MagicMock()
    strategy.power = None
    strategy.shell = MagicMock()
    strategy.sdmux = None
    return strategy


# --- Transition to unknown ---


def test_transition_unknown_raises(strategy_all_drivers):
    with pytest.raises(StrategyError, match="broken state"):
        strategy_all_drivers.transition(Status.unknown)


# --- Transition skip ---


def test_transition_same_status_skips(strategy_all_drivers):
    strategy_all_drivers.status = Status.shell
    strategy_all_drivers.transition(Status.shell)
    # No driver methods called
    assert not strategy_all_drivers.power.off.called


# --- Power off cascade ---


def test_power_off_uses_power_driver(strategy_all_drivers):
    strategy_all_drivers.transition(Status.off)
    strategy_all_drivers.power.off.assert_called_once()


def test_power_off_falls_back_to_shell(strategy_ssh_shell):
    strategy_ssh_shell.transition(Status.off)
    strategy_ssh_shell.shell.run.assert_called_with("poweroff")


def test_power_off_falls_back_to_ssh(strategy_ssh_only):
    strategy_ssh_only.transition(Status.off)
    strategy_ssh_only.ssh.run.assert_called_with("sudo poweroff")


# --- Power on cascade ---


def test_power_on_uses_power_driver(strategy_all_drivers):
    strategy_all_drivers.ssh_boot_timeout = 1
    strategy_all_drivers.power_off_delay = 0
    # Make SSH activate succeed on first try for booted
    strategy_all_drivers.transition(Status.booting)
    strategy_all_drivers.power.on.assert_called_once()


def test_power_on_falls_back_to_shell(strategy_ssh_shell):
    strategy_ssh_shell.power_off_delay = 0
    strategy_ssh_shell.transition(Status.booting)
    # Shell should have been called with reboot (during _power_on)
    # and poweroff (during _power_off in off transition)
    shell_calls = [c.args[0] for c in strategy_ssh_shell.shell.run.call_args_list]
    assert "reboot" in shell_calls


def test_power_on_falls_back_to_ssh(strategy_ssh_only):
    strategy_ssh_only.power_off_delay = 0
    strategy_ssh_only.transition(Status.booting)
    ssh_calls = [c.args[0] for c in strategy_ssh_only.ssh.run.call_args_list]
    assert "sudo reboot" in ssh_calls


# --- SSH connectivity ---


def test_booted_establishes_ssh(strategy_all_drivers):
    strategy_all_drivers.power_off_delay = 0
    strategy_all_drivers.transition(Status.booted)
    strategy_all_drivers.target.activate.assert_any_call(strategy_all_drivers.ssh)
    assert strategy_all_drivers.status == Status.booted


def test_booted_timeout_raises(strategy_ssh_only):
    strategy_ssh_only.power_off_delay = 0
    strategy_ssh_only.ssh_boot_timeout = 1
    # Only fail SSH activate, not deactivate
    original_activate = strategy_ssh_only.target.activate

    def activate_side_effect(driver):
        if driver is strategy_ssh_only.ssh:
            raise Exception("Connection refused")
        return original_activate(driver)

    strategy_ssh_only.target.activate.side_effect = activate_side_effect
    with pytest.raises(StrategyError, match="broken state"):
        strategy_ssh_only.transition(Status.booted)


# --- Shell state ---


def test_shell_transition(strategy_all_drivers):
    strategy_all_drivers.power_off_delay = 0
    strategy_all_drivers.transition(Status.shell)
    assert strategy_all_drivers.status == Status.shell


# --- Soft off ---


def test_soft_off_with_power(strategy_all_drivers):
    strategy_all_drivers.transition(Status.soft_off)
    strategy_all_drivers.power.off.assert_called_once()
    strategy_all_drivers.target.deactivate.assert_any_call(strategy_all_drivers.power)


def test_soft_off_ssh_only(strategy_ssh_only):
    strategy_ssh_only.transition(Status.soft_off)
    strategy_ssh_only.ssh.run.assert_called_with("sudo poweroff")


# --- String status ---


def test_transition_with_string_status(strategy_all_drivers):
    strategy_all_drivers.transition("off")
    assert strategy_all_drivers.status == Status.off


# --- Invalid transition ---


def test_invalid_transition_raises(strategy_all_drivers):
    with pytest.raises(StrategyError):
        strategy_all_drivers.transition(Status.unknown)


# --- Full lifecycle ---


def test_full_lifecycle(strategy_all_drivers):
    strategy_all_drivers.power_off_delay = 0
    strategy_all_drivers.transition(Status.shell)
    assert strategy_all_drivers.status == Status.shell
    strategy_all_drivers.transition(Status.soft_off)
    assert strategy_all_drivers.status == Status.soft_off
