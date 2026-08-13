"""
Driver to control power via a APC PDU using SNMP.
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
        getCmd,
        setCmd,
    )
else:
    from pysnmp.hlapi.v1arch.asyncio import (
        CommunityData,
        SnmpDispatcher,
        UdpTransportTarget,
        get_cmd,
        set_cmd,
    )
    from pysnmp.proto.api.v2c import Integer32
    from pysnmp.smi.rfc1902 import ObjectIdentity, ObjectType


class APCPduException(Exception):
    pass


class APCPdu:
    """
    Class to query & control a APC PDU via SNMP.

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

    async def async_get_outlet_status(self, outlet):
        """Return the APC outlet status code for a single outlet."""
        oid = ObjectIdentity(f"1.3.6.1.4.1.318.1.1.4.4.2.1.3.{outlet}")
        ut = await UdpTransportTarget.create((self.host, 161))

        errorIndication, errorStatus, errorIndex, varBinds = await get_cmd(
            SnmpDispatcher(),
            CommunityData("public"),
            ut,
            ObjectType(oid),
        )

        if errorIndication:
            raise APCPduException(errorIndication)
        if errorStatus:
            raise APCPduException(
                "{} at {}".format(
                    errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                )
            )

        if not varBinds:
            raise APCPduException(f"No SNMP response for outlet {outlet}")

        return int(varBinds[0][1].prettyPrint())

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
            raise APCPduException(errorIndication)
        elif errorStatus:
            raise APCPduException(
                "{} at {}".format(
                    errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                )
            )

    def get_outlet_status(self, outlet):
        """Read the outlet status value synchronously."""
        if Version(__pysnmp_version__) >= Version("7.0.0"):
            return asyncio.run(self.async_get_outlet_status(outlet))

        oid = ObjectIdentity(f"1.3.6.1.4.1.318.1.1.4.4.2.1.3.{outlet}")
        errorIndication, errorStatus, errorIndex, varBinds = next(
            getCmd(
                SnmpEngine(),
                CommunityData("public", mpModel=0),
                UdpTransportTarget((self.host, 161)),
                ContextData(),
                ObjectType(oid),
            )
        )

        if errorIndication:
            raise APCPduException(errorIndication)
        if errorStatus:
            raise APCPduException(
                "{} at {}".format(
                    errorStatus.prettyPrint(),
                    errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                )
            )
        if not varBinds:
            raise APCPduException(f"No SNMP response for outlet {outlet}")

        return int(varBinds[0][1].prettyPrint())

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
                raise APCPduException(errorIndication)
            elif errorStatus:
                raise APCPduException(
                    "{} at {}".format(
                        errorStatus.prettyPrint(),
                        errorIndex and varBinds[int(errorIndex) - 1][0] or "?",
                    )
                )


@target_factory.reg_driver
@attr.s(eq=False)
class APCDriver(Driver, PowerResetMixin, PowerProtocol):
    """APCDriver - Driver using a APC PDU
    to control a target's power
    """

    bindings = {"APC_outlet": {"APCOutlet"}}

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.pdu_dev = APCPdu(self.APC_outlet.address)
        self.outlet = self.APC_outlet.outlet

    @Driver.check_active
    @step()
    def on(self):
        """Turn on the configured APC PDU outlet.

        Uses SNMP to send an 'immediateOn' command to the outlet specified in
        the APCOutlet resource configuration.

        Raises:
            APCPduException: If SNMP communication fails.
        """
        self.pdu_dev.set_outlet_on(self.outlet, True)
        self.logger.debug(f"Powered ON via APC outlet {self.outlet}")

    @Driver.check_active
    @step()
    def off(self):
        """Turn off the configured APC PDU outlet.

        Uses SNMP to send an 'immediateOff' command to the outlet specified in
        the APCOutlet resource configuration.

        Raises:
            APCPduException: If SNMP communication fails.
        """
        self.pdu_dev.set_outlet_on(self.outlet, False)
        self.logger.debug(f"Powered OFF via APC outlet {self.outlet}")

    @Driver.check_active
    @step()
    def reset(self):
        """Perform a power reset cycle on the outlet.

        This method turns off the outlet, waits for the configured delay period,
        then turns it back on. Useful for hard-resetting hardware.

        The delay duration is configured in the APCOutlet resource.

        Raises:
            APCPduException: If SNMP communication fails.
        """
        self.off()
        self.logger.debug("Waiting %.1f seconds before powering ON", self.APC_outlet.delay)
        time.sleep(self.APC_outlet.delay)
        self.on()

    @Driver.check_active
    @step()
    def cycle(self):
        """Power cycle the outlet (same as reset).

        Alias for reset(). Turns off the outlet, waits for the configured delay,
        then turns it back on.

        Raises:
            APCPduException: If SNMP communication fails.
        """
        self.off()
        time.sleep(self.APC_outlet.delay)
        self.on()

    # @Driver.check_active
    # @step()
    # def get(self):
    #     return all(outlet.is_on for outlet in self.outlets)
