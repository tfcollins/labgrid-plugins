"""Unit tests for the BootFabric strategy."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootfabric import BootFabric, Status


@pytest.fixture
def bootfabric_strategy():
    """Create a BootFabric strategy wired to mocked labgrid resources."""
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    strategy = BootFabric(target, "bootfabric")
    strategy.power = None
    strategy.jtag = MagicMock()
    strategy.shell = None
    strategy.ssh = None
    return strategy


def test_booted_requires_verification_when_no_shell(bootfabric_strategy):
    """BootFabric must not claim success without a shell or other boot evidence."""
    with pytest.raises(StrategyError, match="cannot verify boot completion"):
        bootfabric_strategy.transition(Status.booted)


def test_booted_waits_for_marker_when_shell_present(bootfabric_strategy):
    """BootFabric should succeed when the shell reaches the boot marker."""
    shell = MagicMock()
    shell.console.expect.side_effect = [
        (None, b"Linux boot log\n", None, None),
        (None, b"login:\n", None, None),
    ]
    bootfabric_strategy.shell = shell

    bootfabric_strategy.transition(Status.booted)

    assert bootfabric_strategy.status == Status.booted
    shell.console.expect.assert_any_call("Linux", timeout=30)
    shell.console.expect.assert_any_call(
        bootfabric_strategy.reached_boot_marker,
        timeout=bootfabric_strategy.wait_for_boot_timeout,
    )
