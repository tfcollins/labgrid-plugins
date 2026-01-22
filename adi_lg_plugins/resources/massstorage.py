import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class MassStorageDevice(Resource):
    """The MassStorageDevice describes a USB mass storage device

    Args:
        path (str): Path to the mass storage device. Can be device path, sysfs path or USB path.
        file_updates: dict: mapping of source file paths to destination paths on the mass storage device
        use_with_sdmux (bool): Manage state with USBSDMuxDriver if True in strategy. Default: False
    """

    path = attr.ib(validator=attr.validators.instance_of(str))
    file_updates = attr.ib(default={}, validator=attr.validators.instance_of(dict))
    use_with_sdmux = attr.ib(default=False, validator=attr.validators.instance_of(bool))
