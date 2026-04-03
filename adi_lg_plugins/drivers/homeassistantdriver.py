"""
Driver to control power via a Home Assistant switch/outlet using the REST API.
"""

import time

import attr
import requests
from labgrid.driver.common import Driver
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step


class HomeAssistantException(Exception):
    pass


class HomeAssistantClient:
    """Client for Home Assistant REST API switch control.

    :param url: Base URL of the Home Assistant instance
    :param token: Long-lived access token
    """

    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._check_api()

    def _check_api(self):
        """Verify Home Assistant API is reachable."""
        try:
            resp = requests.get(f"{self.url}/api/", headers=self.headers, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise HomeAssistantException(
                f"Failed to connect to Home Assistant at {self.url}: {e}"
            ) from e

    @staticmethod
    def _domain(entity_id):
        """Extract the domain from an entity_id (e.g. 'light.office' -> 'light')."""
        return entity_id.split(".", 1)[0]

    def turn_on(self, entity_id):
        """Turn on an entity."""
        domain = self._domain(entity_id)
        resp = requests.post(
            f"{self.url}/api/services/{domain}/turn_on",
            headers=self.headers,
            json={"entity_id": entity_id},
            timeout=10,
        )
        if not resp.ok:
            raise HomeAssistantException(
                f"Failed to turn on {entity_id}: {resp.status_code} {resp.text}"
            )

    def turn_off(self, entity_id):
        """Turn off an entity."""
        domain = self._domain(entity_id)
        resp = requests.post(
            f"{self.url}/api/services/{domain}/turn_off",
            headers=self.headers,
            json={"entity_id": entity_id},
            timeout=10,
        )
        if not resp.ok:
            raise HomeAssistantException(
                f"Failed to turn off {entity_id}: {resp.status_code} {resp.text}"
            )

    def get_state(self, entity_id):
        """Get the current state of an entity.

        Returns:
            bool: True if the entity state is 'on', False otherwise.
        """
        resp = requests.get(
            f"{self.url}/api/states/{entity_id}",
            headers=self.headers,
            timeout=10,
        )
        if not resp.ok:
            raise HomeAssistantException(
                f"Failed to get state of {entity_id}: {resp.status_code} {resp.text}"
            )
        return resp.json().get("state") == "on"


@target_factory.reg_driver
@attr.s(eq=False)
class HomeAssistantPowerDriver(Driver, PowerResetMixin, PowerProtocol):
    """HomeAssistantPowerDriver - Driver using a Home Assistant switch/outlet
    to control a target's power via the Home Assistant REST API."""

    bindings = {"ha_outlet": {"HomeAssistantOutlet"}}

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.client = HomeAssistantClient(self.ha_outlet.url, self.ha_outlet.token)

    @Driver.check_active
    @step()
    def on(self):
        """Turn on the configured Home Assistant switch."""
        self.client.turn_on(self.ha_outlet.entity_id)
        self.logger.debug("Powered ON via Home Assistant entity %s", self.ha_outlet.entity_id)

    @Driver.check_active
    @step()
    def off(self):
        """Turn off the configured Home Assistant switch."""
        self.client.turn_off(self.ha_outlet.entity_id)
        self.logger.debug("Powered OFF via Home Assistant entity %s", self.ha_outlet.entity_id)

    @Driver.check_active
    @step()
    def reset(self):
        """Power reset: off, delay, on."""
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.ha_outlet.delay)
        time.sleep(self.ha_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle (same as reset)."""
        self.off()
        time.sleep(self.ha_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def get(self):
        """Get the current power state.

        Returns:
            bool: True if the switch is on, False otherwise.
        """
        return self.client.get_state(self.ha_outlet.entity_id)
