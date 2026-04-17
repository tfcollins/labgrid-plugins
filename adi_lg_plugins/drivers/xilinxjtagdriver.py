"""Driver to program Xilinx FPGAs via JTAG using xsdb.

Supports both local execution (test runner == exporter) and remote
execution (test runner ssh's to the exporter host to invoke xsdb).
When any sibling resource on the target is a NetworkResource (has a
`host` attribute), xsdb is run there via ssh and TCL scripts are
pushed via scp; otherwise xsdb runs locally.
"""

import os
import subprocess
import tempfile
import time

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.step import step


@target_factory.reg_driver
@attr.s(eq=False)
class XilinxJTAGDriver(Driver):
    """Program Xilinx FPGAs via JTAG using xsdb.

    Bindings:
        xilinxdevicejtag: XilinxDeviceJTAG resource (JTAG target IDs + bitstream/kernel paths
            as seen by the host that runs xsdb).
        xilinxvivado: XilinxVivadoTool resource (vivado_path / xsdb_path).
    """

    bindings = {
        "xilinxdevicejtag": {"XilinxDeviceJTAG"},
        "xilinxvivado": {"XilinxVivadoTool"},
    }

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("XilinxJTAGDriver initialized")
        self.logger.debug(f"xsdb path: {self.xilinxvivado.xsdb_path}")

    def _remote_host(self):
        """Return exporter host when sibling resources come from a NetworkResource,
        else None (local execution)."""
        for r in getattr(self.target, "resources", ()):
            host = getattr(r, "host", None)
            if host:
                return host
        return None

    def _run_xsdb(self, tcl_script: str):
        """Execute ``tcl_script`` through xsdb, locally or via ssh.

        Returns (stdout, stderr, returncode) as strings.
        """
        host = self._remote_host()
        xsdb = self.xilinxvivado.xsdb_path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
            f.write(tcl_script)
            local_tcl = f.name

        try:
            if host is None:
                result = subprocess.run(
                    [xsdb, local_tcl], capture_output=True, text=True, timeout=300
                )
                return result.stdout, result.stderr, result.returncode

            remote_tcl = f"/tmp/lg_xsdb_{os.getpid()}_{int(time.time() * 1000)}.tcl"
            try:
                subprocess.check_call(["scp", "-q", local_tcl, f"{host}:{remote_tcl}"], timeout=30)
                result = subprocess.run(
                    ["ssh", host, xsdb, remote_tcl],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                return result.stdout, result.stderr, result.returncode
            finally:
                subprocess.call(["ssh", host, "rm", "-f", remote_tcl], timeout=10)
        finally:
            try:
                os.unlink(local_tcl)
            except FileNotFoundError:
                pass

    @Driver.check_active
    @step()
    def connect_jtag(self):
        """Connect to JTAG interface."""
        self.logger.info("Connecting to JTAG")
        tcl_script = """
        connect
        after 1000
        puts "JTAG connected"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"JTAG connection failed: {stderr}")
        self.logger.debug(f"JTAG connection output: {stdout}")

    @Driver.check_active
    @step()
    def flash_bitstream(self):
        """Flash the FPGA bitstream via JTAG."""
        if not self.xilinxdevicejtag.bitstream_path:
            raise ExecutionError("Bitstream path not configured in XilinxDeviceJTAG resource")

        self.logger.info(f"Flashing bitstream: {self.xilinxdevicejtag.bitstream_path}")

        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.root_target}
        after 1000
        fpga -f {self.xilinxdevicejtag.bitstream_path}
        after 2000
        puts "Bitstream flashed successfully"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Bitstream flash failed: {stderr}")
        self.logger.info("Bitstream flashed successfully")
        self.logger.debug(f"Flash output: {stdout}")

    @Driver.check_active
    @step()
    def download_kernel(self):
        """Download Linux kernel image to Microblaze processor."""
        if not self.xilinxdevicejtag.kernel_path:
            raise ExecutionError("Kernel path not configured in XilinxDeviceJTAG resource")

        self.logger.info(f"Downloading kernel: {self.xilinxdevicejtag.kernel_path}")

        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.microblaze_target}
        after 1000
        dow {self.xilinxdevicejtag.kernel_path}
        after 1000
        puts "Kernel downloaded successfully"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Kernel download failed: {stderr}")
        self.logger.info("Kernel downloaded successfully")
        self.logger.debug(f"Download output: {stdout}")

    @Driver.check_active
    @step()
    def start_execution(self):
        """Start kernel execution on Microblaze processor."""
        self.logger.info("Starting kernel execution")
        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.microblaze_target}
        after 1000
        con
        after 500
        puts "Kernel execution started"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Kernel execution failed: {stderr}")
        self.logger.info("Kernel execution started")
        self.logger.debug(f"Execution output: {stdout}")

    @Driver.check_active
    @step()
    def load_bitstream_and_kernel_and_start(self):
        """Load bitstream + kernel, then run the Microblaze."""
        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.root_target}
        after 1000
        fpga -f {self.xilinxdevicejtag.bitstream_path}
        after 2000
        targets {self.xilinxdevicejtag.microblaze_target}
        after 1000
        dow {self.xilinxdevicejtag.kernel_path}
        after 1000
        con
        after 500
        puts "System started"
        """
        self.logger.debug(f"System start TCL script:\n{tcl_script}")
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"System start failed: {stderr}")
        self.logger.debug(f"System start output: {stdout}")

    @Driver.check_active
    @step()
    def disconnect_jtag(self):
        """Disconnect from JTAG interface."""
        self.logger.info("Disconnecting from JTAG")
        tcl_script = """
        disconnect
        puts "JTAG disconnected"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            self.logger.warning(f"JTAG disconnect warning: {stderr}")
        self.logger.debug(f"JTAG disconnect output: {stdout}")
