"""Xilinx Vivado/Vitis tool installation configuration resource."""

import os

import attr
from labgrid.factory import target_factory
from labgrid.resource import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class XilinxVivadoTool(Resource):
    """Xilinx Vivado/Vitis tool installation configuration.

    Stores paths used by the XilinxJTAGDriver; does NOT probe the local
    filesystem, so it round-trips safely through a coordinator (the
    xsdb binary may live only on the exporter host, not the test runner).

    Attributes:
        vivado_path: root of the Vivado install (e.g. "/tools/Xilinx/2025.1/Vivado").
            On newer Xilinx installs the xsdb binary sits under a sibling
            "Vitis/bin" directory, so by default xsdb_path is derived as
            {dirname(vivado_path)}/Vitis/bin/xsdb. Override xsdb_path
            explicitly if your install is laid out differently.
        version: optional Vivado version string (informational).
        xsdb_path: absolute path to xsdb on the host that will run it
            (typically the exporter host). Auto-derived when unset.
    """

    name = attr.ib(default="xilinxvivadotool")

    vivado_path = attr.ib(
        default="/tools/Xilinx/2025.1/Vivado",
        validator=attr.validators.instance_of(str),
    )
    version = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    xsdb_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        if not self.xsdb_path:
            ## Vivado + Vitis are installed side by side; xsdb ships with Vitis.
            ##   /tools/Xilinx/2025.1/Vivado -> /tools/Xilinx/2025.1/Vitis/bin/xsdb
            self.xsdb_path = os.path.join(
                os.path.dirname(self.vivado_path.rstrip("/")), "Vitis", "bin", "xsdb"
            )
