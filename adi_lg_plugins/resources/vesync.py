import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class VesyncOutlet(Resource):
    """The VeSyncOutlet describes a smart outlet controlled with VeSync

    Args:
        outlet_names (str): list of outlet names to control separated by commas
        username (str): VeSync account username (email)
        password (str): VeSync account password
        delay (float, default=5.0): delay between power off and power on during reset operation
    """

    outlet_names = attr.ib(validator=attr.validators.instance_of(str))
    username = attr.ib(validator=attr.validators.instance_of(str))
    password = attr.ib(validator=attr.validators.instance_of(str))
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
