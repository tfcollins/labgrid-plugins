import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class HomeAssistantOutlet(Resource):
    """The HomeAssistantOutlet describes a switch/outlet controlled via Home Assistant REST API

    Args:
        url (str): Base URL of the Home Assistant instance (e.g. http://192.168.1.100:8123)
        token (str): Long-lived access token for Home Assistant authentication
        entity_id (str): Entity ID of the switch to control (e.g. switch.lab_outlet_1)
        delay (float, default=5.0): delay between power off and power on during reset operation
    """

    url = attr.ib(validator=attr.validators.instance_of(str))
    token = attr.ib(validator=attr.validators.instance_of(str))
    entity_id = attr.ib(validator=attr.validators.instance_of(str))
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
