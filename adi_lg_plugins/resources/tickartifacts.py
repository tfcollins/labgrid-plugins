"""Resource describing the per-run Tick deploy artifacts.

Holds host paths to the bitstream, the prebuilt devicetree overlay (.dtbo),
and the kernel module, plus target-side naming used by the Tick deploy
drivers. Pure configuration; declared in a labgrid env config.
"""

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource

_str = attr.validators.instance_of(str)


@target_factory.reg_resource
@attr.s(eq=False)
class TickArtifacts(Resource):
    """Paths and names for the Tick runtime deploy.

    Args:
        bitstream_path (str): Host path to the FPGA ``.bit``.
        overlay_dtbo_path (str): Host path to the prebuilt ``.dtbo`` overlay.
        module_ko_path (str): Host path to ``axi_timed_command_scheduler.ko``.
        firmware_name (str): Name written under ``/lib/firmware`` on target.
        overlay_name (str): configfs overlay directory name.
        remote_dir (str): Scratch directory on the target for staged files.
    """

    bitstream_path = attr.ib(validator=_str)
    overlay_dtbo_path = attr.ib(validator=_str)
    module_ko_path = attr.ib(validator=_str)
    firmware_name = attr.ib(default="tick.bit", validator=_str)
    overlay_name = attr.ib(default="tick", validator=_str)
    remote_dir = attr.ib(default="/tmp/tick", validator=_str)
