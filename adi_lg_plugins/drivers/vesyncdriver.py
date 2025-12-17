"""
Example driver for controlling a network power switch.

This demonstrates how to create a driver in a labgrid plugin.
"""

# import attr

# from labgrid.factory import target_factory
# from labgrid.driver import Driver
# from labgrid.protocol import PowerProtocol
# from labgrid.step import step

import time

import attr

# from labgrid.driver import Driver
from labgrid.driver.common import Driver

# from labgrid.driver.mixin.powerresetmixin import PowerResetMixin
# from labgrid.driver.protocol.powerprotocol import PowerProtocol
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step

# import logging
from pyvesync import VeSync


@target_factory.reg_driver
@attr.s(eq=False)
class VesyncPowerDriver(Driver, PowerResetMixin, PowerProtocol):
    """VesyncPowerDriver - Driver using a Vesync Smart Outlet
    to control a target's power - https://github.com/webdjoe/pyvesync.
    Uses pyvesync tool to control the outlet."""

    bindings = {"vesync_outlet": {"VesyncOutlet"}}

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # self.logger = logging.getLogger(f"{self}")
        # self.logger.debug("Logging into VeSync account")
        self.pdu_dev = VeSync(self.vesync_outlet.username, self.vesync_outlet.password)
        self.pdu_dev.login()
        self.pdu_dev.update()
        self.outlets = []
        if not self.pdu_dev.outlets:
            raise Exception("No VeSync outlets found for this account")
        # Check and store all outlets
        self._known_outlets = [o.device_name for o in self.pdu_dev.outlets]
        outlet_names = self.vesync_outlet.outlet_names.split(",")
        assert len(outlet_names) > 0, "No outlet names provided"
        for name in outlet_names:
            outlet = self._get_outlet_vesync(name.strip())
            self.outlets.append(outlet)
            self.logger.debug(f"Using VeSync outlet: {outlet.device_name}")

    def _get_outlet_vesync(self, name):
        """Get VeSync outlet by name or index"""
        if isinstance(name, str):
            for o in self.pdu_dev.outlets:
                if o.device_name == name:
                    return o
            raise Exception(f"Outlet {name} not found" + f" (known outlets: {self._known_outlets})")
        elif isinstance(name, int):
            if name < 0 or name >= len(self.pdu_dev.outlets):
                raise Exception(f"Outlet index {name} out of range")
            return self.pdu_dev.outlets[name]
        else:
            raise Exception("Outlet must be a string or integer")

    @Driver.check_active
    @step()
    def on(self):
        """Turn on all configured VeSync outlets.

        This method powers on all outlets specified in the VesyncOutlet resource
        configuration. If multiple outlets are configured, they will all be turned
        on sequentially.

        Raises:
            Exception: If outlet control fails or outlets are not found.
        """
        for outlet in self.outlets:
            outlet.turn_on()
        self.logger.debug("Powered ON via Vesync outlet")

    @Driver.check_active
    @step()
    def off(self):
        """Turn off all configured VeSync outlets.

        This method powers off all outlets specified in the VesyncOutlet resource
        configuration. If multiple outlets are configured, they will all be turned
        off sequentially.

        Raises:
            Exception: If outlet control fails or outlets are not found.
        """
        for outlet in self.outlets:
            outlet.turn_off()
        self.logger.debug("Powered OFF via Vesync outlet")

    @Driver.check_active
    @step()
    def reset(self):
        """Perform a power reset cycle on all outlets.

        This method turns off the outlets, waits for the configured delay period,
        then turns them back on. This is useful for hard-resetting hardware.

        The delay duration is configured in the VesyncOutlet resource.

        Raises:
            Exception: If outlet control fails.
        """
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.vesync_outlet.delay)
        time.sleep(self.vesync_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle all outlets (same as reset).

        Alias for reset(). Turns off the outlets, waits for the configured delay,
        then turns them back on.

        Raises:
            Exception: If outlet control fails.
        """
        self.off()
        time.sleep(self.vesync_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def get(self):
        """Get the current power state of all outlets.

        Returns:
            bool: True if all configured outlets are on, False otherwise.
        """
        return all(outlet.is_on for outlet in self.outlets)
