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


# --- boot_mode: BOOT_MODE_USER override (ZynqMP) ----------------------------


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr("adi_lg_plugins.strategies.bootfpgasoc.time.sleep", lambda *_a: None)


def _mode_strategy(boot_mode):
    target = MagicMock()
    target.bind.side_effect = lambda item: setattr(item, "target", target)
    strategy = BootFPGASoC(target, "boot", boot_mode=boot_mode)
    strategy.status = Status.sd_mux_to_dut
    strategy.power = MagicMock()
    strategy.jtag = MagicMock()
    strategy.jtag.set_zynqmp_boot_mode.return_value = {
        "effective_name": boot_mode,
        "pins_name": "jtag",
    }
    strategy.jtag.get_zynqmp_boot_mode.return_value = {
        "raw": 0x100,
        "effective": 0,
        "use_alt": True,
        "pins_name": "sd1-ls",
    }
    return strategy


def test_booting_applies_a_device_boot_mode_after_power_on(no_sleep):
    strategy = _mode_strategy("sd1-ls")
    order = []
    strategy.power.on.side_effect = lambda: order.append(("on",))

    def override(*args, **kwargs):
        order.append(("override", *args))
        return {"effective_name": "sd1-ls", "pins_name": "jtag"}

    strategy.jtag.set_zynqmp_boot_mode.side_effect = override

    strategy.transition(Status.booting)

    assert order == [("on",), ("override", "sd1-ls")]
    assert strategy.status is Status.booting


def test_booting_without_boot_mode_leaves_jtag_alone(no_sleep):
    strategy = _mode_strategy(None)
    strategy.transition(Status.booting)
    strategy.jtag.set_zynqmp_boot_mode.assert_not_called()


def test_boot_mode_needs_the_jtag_binding(no_sleep):
    strategy = _mode_strategy("sd1-ls")
    strategy.jtag = None
    with pytest.raises(StrategyError, match="XilinxJTAGDriver"):
        strategy.transition(Status.booting)


def test_jtag_boot_mode_state_holds_the_board_at_the_bootrom(no_sleep):
    strategy = _mode_strategy(None)
    strategy.shell = MagicMock()
    strategy.status = Status.unknown

    strategy.transition(Status.jtag_boot_mode)

    strategy.power.on.assert_called_once()
    strategy.jtag.set_zynqmp_boot_mode.assert_called_once_with(
        "jtag", reset=True, jtag_url="TCP:127.0.0.1:3121"
    )
    assert strategy.status is Status.jtag_boot_mode


def test_boot_mode_jtag_cannot_boot_linux(no_sleep):
    strategy = _mode_strategy("jtag")
    with pytest.raises(StrategyError, match="jtag_boot_mode state"):
        strategy.transition(Status.booted)
    strategy.power.on.assert_not_called()
