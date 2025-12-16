import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class KuiperRelease(Resource):
    """The KuiperRelease describes a Kuiper release resource

    Args:
        release_version (str): Version of the Kuiper release to download and manage.
        cache_path (str): Path to cache the downloaded Kuiper release. Defaults to /home/<user>/.labgrid/kuiper_releases/
        kernel_path (str): Path to the kernel file to use with the Kuiper release.
        BOOTBIN_path (str): Path to the BOOTBIN file to use with the Kuiper release.
        device_tree_path (str): Path to the device tree file to use with the Kuiper release.
    """

    release_version = attr.ib(validator=attr.validators.instance_of(str))
    cache_path = attr.ib(
        default="~/.labgrid/kuiper_releases/",
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    kernel_path = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    BOOTBIN_path = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    device_tree_path = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
