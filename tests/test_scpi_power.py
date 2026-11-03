"""ScpiPowerDriver against a fake SCPI supply on a local TCP socket."""

import socketserver
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from labgrid.driver.common import BindingState

from adi_lg_plugins.drivers.scpidriver import ScpiPowerDriver, scpi_power


class _Supply(socketserver.StreamRequestHandler):
    def handle(self):
        for raw in self.rfile:
            line = raw.decode().strip()
            self.server.commands.append(line)
            if line == "SYST:ERR?":
                self.wfile.write(
                    b'-221,"Settings conflict"\n' if self.server.fail else b'+0,"No error"\n'
                )
            elif line.startswith("OUTP?"):
                channel = line.split("@")[1].rstrip(")")
                self.wfile.write(b"1\n" if channel in self.server.on else b"0\n")
            elif line.startswith("OUTP ON"):
                self.server.on |= set(line.split("@")[1].rstrip(")").split(","))
            elif line.startswith("OUTP OFF"):
                self.server.on -= set(line.split("@")[1].rstrip(")").split(","))


@pytest.fixture
def supply():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Supply)
    server.commands, server.on, server.fail = [], set(), False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()
    server.server_close()


def test_on_and_off_switch_the_named_channels(supply):
    host, port = supply.server_address

    scpi_power("on", host, port, "1, 2")
    assert supply.on == {"1", "2"}
    assert "OUTP ON,(@1,2)" in supply.commands

    scpi_power("off", host, port, "1,2")
    assert supply.on == set()


def test_get_is_true_only_when_every_channel_is_on(supply):
    host, port = supply.server_address
    supply.on = {"1"}

    assert scpi_power("get", host, port, "1,2") is False
    supply.on = {"1", "2"}
    assert scpi_power("get", host, port, "1,2") is True


def test_a_supply_error_is_raised(supply):
    host, port = supply.server_address
    supply.fail = True

    with pytest.raises(RuntimeError, match="Settings conflict"):
        scpi_power("on", host, port, "1")


@pytest.mark.parametrize("channels", ["", "1;*RST", "a", "1,,2"])
def test_channels_that_are_not_numbers_are_refused_before_connecting(channels):
    with pytest.raises(ValueError, match="channels"):
        scpi_power("on", "192.0.2.1", 5025, channels)


def _driver(resource):
    driver = ScpiPowerDriver.__new__(ScpiPowerDriver)
    driver.scpi_supply = resource
    driver.logger = MagicMock()
    driver.state = BindingState.active
    driver._init_exporter_agent()
    return driver


def test_local_driver_uses_the_socket(supply):
    host, port = supply.server_address
    driver = _driver(SimpleNamespace(host=host, port=port, channels="1,2", delay=0.0, extra=None))

    driver.on()
    assert driver.get() is True
    driver.off()
    assert driver.get() is False


def test_remote_driver_uses_the_exporter_agent():
    resource = SimpleNamespace(
        extra={"proxy": "exporter.example.com"},
        host="192.168.10.31",
        port=5025,
        channels="1,2",
        delay=0.0,
    )
    driver = _driver(resource)
    driver._agent_module = MagicMock()
    driver._agent_module.scpi.return_value = True

    driver.on()
    driver.off()
    assert driver.get() is True

    common = ("192.168.10.31", 5025, "1,2")
    driver._agent_module.scpi.assert_any_call("on", *common)
    driver._agent_module.scpi.assert_any_call("off", *common)
    driver._agent_module.scpi.assert_any_call("get", *common)
