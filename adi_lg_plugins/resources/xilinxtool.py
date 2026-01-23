"""Xilinx Vivado/Vitis tool installation configuration resource."""

import os
import subprocess
import tempfile

import attr
from labgrid.resource import Resource
from labgrid.factory import target_factory


@target_factory.reg_resource
@attr.s(eq=False)
class XilinxVivadoTool(Resource):
    """Xilinx Vivado/Vitis tool installation configuration.

    Specifies paths to Xilinx tools (xsdb, xsct) for JTAG operations.
    Automatically locates xsdb binary and provides methods to execute
    TCL scripts via xsdb.

    Attributes:
        vivado_path (str): Root path to Xilinx Vivado installation (default: "/tools/Xilinx/Vivado").
            Example: "/opt/Xilinx/Vivado" or "/tools/Xilinx/Vivado"
        version (str, optional): Vivado version string (e.g., "2023.2", "2022.1").
            If not specified, automatically selects latest version found in vivado_path.
    """

    name = attr.ib(default="xilinxvivadotool")

    # Vivado installation path
    vivado_path = attr.ib(
        default="/tools/Xilinx/Vivado",
        validator=attr.validators.instance_of(str),
    )

    # Version (e.g., "2023.2")
    version = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    # Derived paths (computed in __attrs_post_init__)
    xsdb_path = attr.ib(init=False, default=None)

    def __attrs_post_init__(self):
        """Initialize xsdb_path based on vivado_path and version."""
        super().__attrs_post_init__()

        if self.version:
            # Use explicit version
            xsdb = os.path.join(self.vivado_path, self.version, "bin", "xsdb")
        else:
            # Search for latest version
            if not os.path.exists(self.vivado_path):
                raise ValueError(f"Vivado path does not exist: {self.vivado_path}")

            versions = sorted(
                [d for d in os.listdir(self.vivado_path) if os.path.isdir(os.path.join(self.vivado_path, d))],
                reverse=True,
            )

            if not versions:
                raise ValueError(f"No Vivado versions found in {self.vivado_path}")

            self.version = versions[0]
            xsdb = os.path.join(self.vivado_path, self.version, "bin", "xsdb")

        if not os.path.exists(xsdb):
            raise ValueError(f"xsdb not found at {xsdb}")

        self.xsdb_path = xsdb

    def run_xsdb_script(self, tcl_script: str) -> tuple:
        """Execute TCL script via xsdb.

        Args:
            tcl_script (str): TCL commands to execute. Will be written to a temporary
                file and executed by xsdb.

        Returns:
            tuple: (stdout, stderr, returncode) where stdout and stderr are strings.

        Raises:
            RuntimeError: If xsdb execution fails or times out.

        Example:
            >>> tool = XilinxVivadoTool()
            >>> stdout, stderr, rc = tool.run_xsdb_script(
            ...     "connect\\nafter 1000\\nfpga -f design.bit\\ndisconnect"
            ... )
            >>> if rc == 0:
            ...     print("Success:", stdout)
            ... else:
            ...     print("Error:", stderr)
        """
        # Write TCL to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
            f.write(tcl_script)
            tcl_file = f.name

        try:
            # Execute xsdb with script
            result = subprocess.run(
                [self.xsdb_path, tcl_file],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.stdout, result.stderr, result.returncode
        finally:
            # Clean up temporary file
            if os.path.exists(tcl_file):
                os.unlink(tcl_file)
