"""Xilinx Vivado/Vitis tool installation configuration resource."""

import os
import subprocess
import tempfile
import glob

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
        vivado_path (str, optional): Root path to Xilinx Vivado installation
            (default: "/tools/Xilinx/Vivado").
            Example: "/opt/Xilinx/Vivado/2023.2" or "/tools/Xilinx/2025.1/Vivado"
        version (str, optional): Vivado version string (e.g., "2023.2").
            Used to locate vivado_path if not explicitly set.
    """

    name = attr.ib(default="xilinxvivadotool")

    # Vivado installation path
    vivado_path = attr.ib(
        default="/tools/Xilinx/2025.1/Vivado",
        validator=attr.validators.instance_of(str),
    )

    # Version (e.g., "2023.2")
    version = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    # Derived paths (computed in __attrs_post_init__)
    xsdb_path = attr.ib(init=False, default=None)
    settings_path = attr.ib(init=False, default=None)

    def __attrs_post_init__(self):
        """Initialize xsdb_path based on vivado_path and version."""
        super().__attrs_post_init__()

        if self.vivado_path:
            if not os.path.exists(self.vivado_path):
                raise ValueError(f"Vivado path does not exist: {self.vivado_path}")

        else:
            if not self.version:
                raise ValueError("Either vivado_path or version must be specified")
            path1 = f"/tools/Xilinx/{self.version}/Vivado"
            path2 = f"/opt/Xilinx/Vivado/{self.version}"
            path3 = f"/opt/Xilinx/{self.version}/Vivado"
            for p in (path1, path2, path3):
                if os.path.exists(p):
                    self.vivado_path = p
                    break
            if not self.vivado_path:
                raise ValueError(f"Vivado path not found for version {self.version}")
        # Use glob to find settings.sh
        files = glob.glob(os.path.join(self.vivado_path, "**", "settings64.sh"), recursive=True)
        if not files:
            raise ValueError(f"settings64.sh not found in {self.vivado_path}")
        self.settings_path = files[0]
        self.logger.info(f"Found Vivado settings script at: {self.settings_path}")

        # Source script and find xsdb
        cmd = f"bash -c 'source {self.settings_path} && which xsdb'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise ValueError(f"Failed to locate xsdb: {result.stderr.strip()}")
        xsdb = result.stdout.strip()
        if not os.path.exists(xsdb):
            raise ValueError(f"xsdb not found at {xsdb}")
        self.logger.info(f"xsdb located at: {xsdb}")

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
