"""SCPI bench-supply power driver for labgrid.

Switches the outputs of a LAN bench supply (Keysight E36200 series, ...) with
``OUTP ON|OFF,(@<channels>)`` over a raw TCP socket, and reads their state back
with ``OUTP? (@<channel>)``. No extra Python dependency: the supply speaks plain
text on port 5025.

The supply is usually reachable only from the exporter's network, so against a
RemotePlace the work runs in the exporter's power agent (``adi_power.scpi``).
"""

import re
import socket
import time

import attr
from labgrid.driver.common import Driver
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step

from ._power_agent import ExporterPowerAgentMixin

_CHANNELS = re.compile(r"^\d+(,\d+)*$")
_TIMEOUT = 5.0


def scpi_power(action, host, port, channels):
    """Run ``on``/``off``/``get`` on ``channels`` of the supply; ``get`` returns True if all are on."""
    channels = channels.replace(" ", "")
    if not _CHANNELS.match(channels):
        raise ValueError(f"SCPI channels must be digits separated by commas, got {channels!r}")
    if action not in {"on", "off", "get"}:
        raise ValueError(f"unsupported SCPI action: {action!r}")
    with socket.create_connection((host, port), timeout=_TIMEOUT) as sock:
        stream = sock.makefile("rw", newline="\n")
        if action == "get":
            states = []
            for channel in channels.split(","):
                stream.write(f"OUTP? (@{channel})\n")
                stream.flush()
                states.append(stream.readline().strip() in {"1", "ON"})
            return all(states)
        stream.write(f"OUTP {action.upper()},(@{channels})\n")
        stream.write("SYST:ERR?\n")
        stream.flush()
        error = stream.readline().strip()
        if not error.startswith("+0") and not error.startswith("0"):
            raise RuntimeError(f"SCPI supply at {host} rejected OUTP {action}: {error}")
    return None


@target_factory.reg_driver
@attr.s(eq=False)
class ScpiPowerDriver(ExporterPowerAgentMixin, Driver, PowerResetMixin, PowerProtocol):
    """Driver controlling a target's power via a SCPI bench supply's outputs."""

    bindings = {"scpi_supply": {"ScpiPowerSupply"}}
    _remote_binding = "scpi_supply"

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self._init_exporter_agent()

    def _run(self, action):
        res = self.scpi_supply
        if self._is_remote:
            return self._exporter_call("scpi", action, res.host, res.port, res.channels)
        return scpi_power(action, res.host, res.port, res.channels)

    @Driver.check_active
    @step()
    def on(self):
        """Turn on all configured supply outputs."""
        self._run("on")
        self.logger.debug("Powered ON via SCPI supply")

    @Driver.check_active
    @step()
    def off(self):
        """Turn off all configured supply outputs."""
        self._run("off")
        self.logger.debug("Powered OFF via SCPI supply")

    @Driver.check_active
    @step()
    def reset(self):
        """Power cycle: turn off, wait ``delay`` seconds, turn back on."""
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.scpi_supply.delay)
        time.sleep(self.scpi_supply.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle all outputs (alias for reset)."""
        self.reset()

    @Driver.check_active
    @step()
    def get(self):
        """Return True if all configured outputs are on."""
        return self._run("get")
