"""Hardware smoke test for the BootVPK180 strategy.

Requires --run-hardware and a labgrid YAML with a fully-wired VPK180 target:
power (HomeAssistantPowerDriver), sc_shell + target_shell (ADIShellDriver
on ttyUSB3 / ttyUSB1 respectively), and a configured ``sc_commands`` list.
"""

import pytest

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def in_shell(strategy):
    strategy.transition("shell")
    yield


def test_full_boot_to_shell(strategy, in_shell):
    """End-to-end: powered_off → shell. Verifies SC orchestration + Versal boot."""
    from adi_lg_plugins.strategies.bootvpk180 import Status

    assert strategy.status == Status.shell
    assert strategy.boot_log, "boot_log should capture UART output across boot phases"


def test_target_console_responsive(target, in_shell):
    """After shell, the Versal target console should respond to a basic command."""
    # Two ADIShellDrivers are bound (sc_shell + target_shell); pick by name.
    target_shell = target.get_driver("ADIShellDriver", name="target_shell")
    stdout, _, returncode = target_shell.run("uname -a")
    print(stdout)
    assert returncode == 0
    assert stdout
    assert "Linux" in stdout[0]

    stdout, _, returncode = target_shell.run("ip -4 addr")
    print(stdout)


def test_soft_off_powers_down(strategy, in_shell):
    """Soft-off attempts a graceful poweroff before falling back to hard cut."""
    from adi_lg_plugins.strategies.bootvpk180 import Status

    strategy.transition("soft_off")
    assert strategy.status == Status.soft_off
