import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class CyberPowerOutlet(Resource):
    """The CyberPowerOutlet describes a smart outlet controlled with CyberPower

    Args:
        address (str): IP address of the CyberPower PDU
        outlet (int): Outlet number on the PDU to control
        delay (float, default=5.0): delay between power off and power on during reset operation
    """

    address = attr.ib(validator=attr.validators.instance_of(str))
    outlet = attr.ib(validator=attr.validators.instance_of(int))
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
