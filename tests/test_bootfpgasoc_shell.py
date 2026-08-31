from unittest.mock import MagicMock

import pytest
from labgrid.strategy import Strategy, StrategyError

from adi_lg_plugins.strategies.bootfpgasoc import BootFPGASoC, Status


@pytest.fixture(autouse=True)
def light_post_init(monkeypatch):
    def _post_init(self):
        Strategy.__attrs_post_init__(self)
        for name in type(self).bindings:
            if not hasattr(self, name):
                setattr(self, name, None)

    monkeypatch.setattr(BootFPGASoC, "__attrs_post_init__", _post_init)


def _strategy(returncode=0):
    target = MagicMock()
    target.bind.side_effect = lambda item: setattr(item, "target", target)
    strategy = BootFPGASoC(target, "boot")
    strategy.status = Status.booted
    strategy.shell = MagicMock()
    strategy.shell.run.return_value = ([], [], returncode)
    return strategy


def test_shell_transition_restarts_iiod_after_driver_probe():
    strategy = _strategy()

    strategy.transition(Status.shell)

    command = strategy.shell.run.call_args.args[0]
    assert "systemctl restart iiod.service" in command
    assert strategy.status is Status.shell


def test_shell_transition_fails_when_iiod_cannot_restart():
    strategy = _strategy(returncode=1)
    strategy.shell.run.return_value = ([], ["unit failed"], 1)

    with pytest.raises(StrategyError, match="unit failed"):
        strategy.transition(Status.shell)


def test_shell_transition_can_leave_iiod_untouched():
    strategy = _strategy()
    strategy.restart_iiod_on_shell = False

    strategy.transition(Status.shell)

    strategy.shell.run.assert_not_called()


def test_net_refresh_syncs_ssh_ip_with_dhcp():
    strategy = _strategy()
    strategy.ssh = MagicMock()
    strategy.ssh.networkservice.address = "192.168.1.50"

    mock_ip = MagicMock()
    mock_ip.ip = "192.168.1.100"
    strategy.shell.get_ip_addresses.return_value = [mock_ip]
    strategy.trigger_dhcp_request = True
    strategy.ethernet_interface = "eth0"

    strategy.transition(Status.net_refresh)

    calls = [call[0][0] for call in strategy.shell.run.call_args_list]
    assert any("dhclient -r eth0" in c for c in calls)
    assert any("dhclient eth0" in c for c in calls)
    assert strategy.ssh.networkservice.address == "192.168.1.100"
    assert strategy.status is Status.net_refresh


def test_net_refresh_skips_dhcp_when_disabled():
    strategy = _strategy()
    strategy.ssh = MagicMock()
    strategy.ssh.networkservice.address = "192.168.1.50"

    mock_ip = MagicMock()
    mock_ip.ip = "192.168.1.100"
    strategy.shell.get_ip_addresses.return_value = [mock_ip]
    strategy.trigger_dhcp_request = False

    strategy.transition(Status.net_refresh)

    strategy.shell.run.assert_not_called()
    assert strategy.ssh.networkservice.address == "192.168.1.100"
    assert strategy.status is Status.net_refresh


def test_net_refresh_no_ssh_skips_sync():
    strategy = _strategy()
    strategy.ssh = None

    strategy.transition(Status.net_refresh)

    strategy.shell.run.assert_not_called()
    strategy.shell.get_ip_addresses.assert_not_called()
    assert strategy.status is Status.net_refresh
