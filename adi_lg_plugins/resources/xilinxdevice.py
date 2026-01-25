"""Xilinx FPGA device JTAG configuration resource."""

import attr
from labgrid.factory import target_factory
from labgrid.resource import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class XilinxDeviceJTAG(Resource):
    """Xilinx FPGA device JTAG configuration.

    Defines JTAG target IDs and file paths for Virtex/Artix/Kintex FPGAs
    with Microblaze soft processors.

    Attributes:
        root_target (int): JTAG target ID for root device (default: 1).
            This is typically the FPGA fabric target identified by xsdb 'targets' command.
        microblaze_target (int): JTAG target ID for Microblaze processor (default: 3).
            This is typically the processor core target for xsdb commands.
        bitstream_path (str, optional): Path to FPGA bitstream file (.bit).
            Required when using BootFabric strategy. Must exist on filesystem.
        kernel_path (str, optional): Path to Microblaze Linux kernel image (.strip).
            Required when using BootFabric strategy. Must exist on filesystem.
        devicetree_path (str, optional): Path to device tree binary (.dtb).
            Only needed if device tree is separate from kernel image.
    """

    name = attr.ib(default="xilinxdevicejtag")

    # JTAG target IDs (from xsdb 'targets' command output)
    root_target = attr.ib(
        default=1,
        validator=attr.validators.instance_of(int),
    )
    microblaze_target = attr.ib(
        default=3,
        validator=attr.validators.instance_of(int),
    )

    # File paths
    bitstream_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    kernel_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    # Optional device tree (if not embedded in kernel)
    devicetree_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
