import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class ScpiPowerSupply(Resource):
    """The ScpiPowerSupply describes a LAN bench supply that takes SCPI over a raw socket.

    Written for the Keysight E36200 series (E36233A, ...), which listen on TCP
    port 5025. The driver switches the outputs with ``OUTP ON|OFF,(@<channels>)``.

    Args:
        host (str): IP address or hostname of the supply.
        channels (str, default="1"): Output channel(s) to switch, comma-separated
            (``"1,2"``).
        port (int, default=5025): SCPI raw-socket TCP port.
        delay (float, default=5.0): delay between power off and power on during
            reset or cycle operations.
    """

    host = attr.ib(validator=attr.validators.instance_of(str))
    channels = attr.ib(default="1", validator=attr.validators.instance_of(str))
    port = attr.ib(default=5025, validator=attr.validators.instance_of(int))
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
