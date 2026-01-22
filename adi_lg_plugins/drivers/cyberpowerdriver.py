"""
Driver to control power via a CyberPower PDU using SNMP.
"""

import asyncio
import time

import attr
from labgrid.driver.common import Driver
from labgrid.driver.powerdriver import PowerResetMixin
from labgrid.factory import target_factory
from labgrid.protocol import PowerProtocol
from labgrid.step import step
from packaging.version import Version

try:
    from pysnmp import __version__ as __pysnmp_version__

    # Ensure we have a string version (not a mock object)
    if not isinstance(__pysnmp_version__, str):
        __pysnmp_version__ = "7.0.0"
except (ImportError, AttributeError):
    # During Sphinx doc building or when pysnmp is not available,
    # default to the newer API
    __pysnmp_version__ = "7.0.0"

if Version(__pysnmp_version__) < Version("7.0.0"):
    from pysnmp.hlapi import (
        CommunityData,
        ContextData,
        Integer32,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        setCmd,
    )
else:
    from pysnmp.hlapi.v1arch.asyncio import (
        CommunityData,
        SnmpDispatcher,
        UdpTransportTarget,
        set_cmd,
    )
    from pysnmp.proto.api.v2c import Integer32
    from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType


class CyberPowerPduException(Exception):
    pass


class CyberPowerPdu:
    """
    Class to query & control a CyberPower PDU via SNMP.

    Tested on the PDU15SWHVIEC8FNET. I don't understand SNMP well enough to have
    any idea if this would be expected to work on other models.

    This class is basically just a piece of copy-pasted pysnmp code and a
    depository for comments.

    :param host: IP address or hostname of the PDU on the network
    :type host: str
    """

    outlet_state_oids = {
        "immediateOn": 1,
        "immediateOff": 2,
        "immediateReboot": 3,
        "delayedOn": 4,
        "delayedOff": 5,
        "delayedReboot": 6,
        "cancelPendingCommand": 7,
        "outletIdentify": 8,
    }

    def __init__(self, host):
        self.host = host

    async def async_set_outlet_on(self, outlet, on):
        """
        Set an outlet on or off (async version for pysnmp >= 7.0.0)

        :param outlet: Which outlet to set the power for (for my model this is
                       in the range 1 through 8)
        :param on: INVALID ATM True means turn it on, False means turn it off
        """

        oid = ObjectIdentity(f"1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.{outlet}")
        if isinstance(on, bool):
            target_state = "immediateOn" if on else "immediateOff"
        else:
            target_state = on

        # Create transport target asynchronously
        ut = await UdpTransportTarget.create((self.host, 161))

        # Use set_cmd and await it (v1arch API for pysnmp >= 7.0.0)
        errorIndication, errorStatus, errorIndex, varBinds = await set_cmd(
            SnmpDispatcher(),
            CommunityData("private"),
            ut,
            ObjectType(oid, Integer32(self.outlet_state_oids[target_state])),
        )

        if errorIndication:
            raise CyberPowerPduException(errorIndication)
        elif errorStatus:
            raise CyberPowerPduException(
                "{} at {}".format(
                    errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                )
            )

    def set_outlet_on(self, outlet, on):
        """
        Set an outlet on or off (synchronous wrapper)

        :param outlet: Which outlet to set the power for (for my model this is
                       in the range 1 through 8)
        :param on: INVALID ATM True means turn it on, False means turn it off
        """
        if Version(__pysnmp_version__) >= Version("7.0.0"):
            # For pysnmp >= 7.0.0, use async version
            return asyncio.run(self.async_set_outlet_on(outlet, on))
        else:
            # For pysnmp < 7.0.0, use synchronous version
            oid = ObjectIdentity(f"1.3.6.1.4.1.3808.1.1.3.3.3.1.1.4.{outlet}")
            if isinstance(on, bool):
                target_state = "immediateOn" if on else "immediateOff"
            else:
                target_state = on

            errorIndication, errorStatus, errorIndex, varBinds = next(
                setCmd(
                    SnmpEngine(),
                    CommunityData("private"),
                    UdpTransportTarget((self.host, 161)),
                    ContextData(),
                    ObjectType(oid, Integer32(self.outlet_state_oids[target_state])),
                )
            )

            if errorIndication:
                raise CyberPowerPduException(errorIndication)
            elif errorStatus:
                raise CyberPowerPduException(
                    "{} at {}".format(
                        errorStatus.prettyPrint(),
                        errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                    )
                )


@target_factory.reg_driver
@attr.s(eq=False)
class CyberPowerDriver(Driver, PowerResetMixin, PowerProtocol):
    """CyberPowerDriver - Driver using a CyberPower PDU
    to control a target's power
    """

    bindings = {"cyberpower_outlet": {"CyberPowerOutlet"}}

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.pdu_dev = CyberPowerPdu(self.cyberpower_outlet.address)
        self.outlet = self.cyberpower_outlet.outlet

    @Driver.check_active
    @step()
    def on(self):
        """Turn on the configured CyberPower PDU outlet.

        Uses SNMP to send an 'immediateOn' command to the outlet specified in
        the CyberPowerOutlet resource configuration.

        Raises:
            CyberPowerPduException: If SNMP communication fails.
        """
        self.pdu_dev.set_outlet_on(self.outlet, True)
        self.logger.debug(f"Powered ON via CyberPower outlet {self.outlet}")

    @Driver.check_active
    @step()
    def off(self):
        """Turn off the configured CyberPower PDU outlet.

        Uses SNMP to send an 'immediateOff' command to the outlet specified in
        the CyberPowerOutlet resource configuration.

        Raises:
            CyberPowerPduException: If SNMP communication fails.
        """
        self.pdu_dev.set_outlet_on(self.outlet, False)
        self.logger.debug(f"Powered OFF via CyberPower outlet {self.outlet}")

    @Driver.check_active
    @step()
    def reset(self):
        """Perform a power reset cycle on the outlet.

        This method turns off the outlet, waits for the configured delay period,
        then turns it back on. Useful for hard-resetting hardware.

        The delay duration is configured in the CyberPowerOutlet resource.

        Raises:
            CyberPowerPduException: If SNMP communication fails.
        """
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.cyberpower_outlet.delay)
        time.sleep(self.cyberpower_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle the outlet (same as reset).

        Alias for reset(). Turns off the outlet, waits for the configured delay,
        then turns it back on.

        Raises:
            CyberPowerPduException: If SNMP communication fails.
        """
        self.off()
        time.sleep(self.cyberpower_outlet.delay)
        self.on()

    # @Driver.check_active
    # @step()
    # def get(self):
    #     return all(outlet.is_on for outlet in self.outlets)
