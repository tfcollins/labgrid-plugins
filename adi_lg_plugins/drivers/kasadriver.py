"""Kasa (TP-Link) power driver for labgrid.

Controls a TP-Link Kasa smart plug or power strip over the local network
using the ``python-kasa`` library (https://github.com/python-kasa/python-kasa).
Single plugs are controlled as one outlet; power strips expose each socket as
a child selectable by index or alias.

``python-kasa`` is async; each ``PowerProtocol`` method runs a short coroutine
via ``asyncio.run``. Every operation connects fresh, updates, acts on the
resolved sockets, then disconnects — power operations are infrequent, so the
reconnect cost is irrelevant and it avoids stale-connection / event-loop reuse
issues.
"""

import asyncio
import time

import attr
from kasa import Discover
from labgrid.driver.common import Driver
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step


@target_factory.reg_driver
@attr.s(eq=False)
class KasaPowerDriver(Driver, PowerResetMixin, PowerProtocol):
    """Driver controlling a target's power via a TP-Link Kasa device."""

    bindings = {"kasa_outlet": {"KasaOutlet"}}

    async def _connect(self):
        """Discover and return a connected, updated Kasa device."""
        res = self.kasa_outlet
        kwargs = {}
        if res.username and res.password:
            kwargs["username"] = res.username
            kwargs["password"] = res.password
        device = await Discover.discover_single(res.host, **kwargs)
        if device is None:
            raise Exception(f"No Kasa device found at {res.host!r}")
        await device.update()
        return device

    def _resolve_outlets(self, device):
        """Return the list of device/child objects this driver controls.

        With no ``outlets`` selector, a strip's children are all returned and
        a single plug returns itself. A selector resolves each comma token by
        0-based index or by alias.
        """
        selector = self.kasa_outlet.outlets
        children = list(device.children)
        if not selector:
            return children if children else [device]

        targets = []
        for token in selector.split(","):
            token = token.strip()
            if not token:
                continue
            targets.append(self._get_child(device, children, token))
        return targets

    @staticmethod
    def _get_child(device, children, token):
        """Resolve a single selector token to a child socket."""
        if token.lstrip("-").isdigit():
            index = int(token)
            if index < 0 or index >= len(children):
                raise Exception(
                    f"Kasa outlet index {index} out of range (device has {len(children)} children)"
                )
            return children[index]
        for child in children:
            if child.alias == token:
                return child
        known = [c.alias for c in children]
        raise Exception(f"Kasa outlet {token!r} not found (known outlets: {known})")

    async def _apply(self, action):
        """Connect, run ``action`` ('turn_on'/'turn_off') on each outlet, close."""
        device = await self._connect()
        try:
            for outlet in self._resolve_outlets(device):
                await getattr(outlet, action)()
        finally:
            await device.disconnect()

    async def _is_on(self):
        """Connect and return whether all controlled outlets are on."""
        device = await self._connect()
        try:
            return all(outlet.is_on for outlet in self._resolve_outlets(device))
        finally:
            await device.disconnect()

    @Driver.check_active
    @step()
    def on(self):
        """Turn on all configured Kasa outlets."""
        asyncio.run(self._apply("turn_on"))
        self.logger.debug("Powered ON via Kasa outlet")

    @Driver.check_active
    @step()
    def off(self):
        """Turn off all configured Kasa outlets."""
        asyncio.run(self._apply("turn_off"))
        self.logger.debug("Powered OFF via Kasa outlet")

    @Driver.check_active
    @step()
    def reset(self):
        """Power cycle: turn off, wait ``delay`` seconds, turn back on."""
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.kasa_outlet.delay)
        time.sleep(self.kasa_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle all outlets (alias for reset)."""
        self.reset()

    @Driver.check_active
    @step()
    def get(self):
        """Return True if all configured Kasa outlets are on."""
        return asyncio.run(self._is_on())
