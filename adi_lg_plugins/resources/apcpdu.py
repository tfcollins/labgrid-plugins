import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class APCOutlet(Resource):
    """The APCOutlet describes an APC smart PDU outlet.

    Args:
        address (str): IP address or hostname of the APC PDU.
        outlet (int): Outlet number to control on the PDU.
        delay (float, default=5.0): delay between power off and power on during
            reset or cycle operations.
    """

    address = attr.ib(validator=attr.validators.instance_of(str))
    outlet = attr.ib(validator=attr.validators.instance_of(int))
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
