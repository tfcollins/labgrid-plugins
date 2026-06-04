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

    @Driver.check_active
    @step()
    def load_zynq_uboot(
        self,
        ps7_init_tcl: str,
        uboot_elf: str,
        a9_target_name: str = "*Cortex-A9 MPCore #0",
        bitstream_path: str | None = None,
        fsbl_elf: str | None = None,
    ) -> None:
        """JTAG-bootstrap U-Boot on a Zynq-7000 device.

        The board can be in any boot state — xsdb will ``rst -system`` first
        to clear residual DDR/PS state before sourcing the board-specific
        ``ps7_init.tcl``. Used for SD-card recovery when BootROM cannot load
        FSBL from a corrupted card.

        The ``a9_target_name`` filter is used instead of an integer target
        index because Zynq-7000 xsdb target ordering shifts when the PL is
        loaded; the name-pattern form matches Xilinx's generated wrappers
        and is stable across Vivado versions.
        """
        self.logger.info(f"JTAG-bootstrapping Zynq-7000 U-Boot from {uboot_elf}")

        optional_lines = []
        if bitstream_path:
            optional_lines.append(f"fpga -f {bitstream_path}")
            optional_lines.append("after 2000")
        optional_lines.append(f"source {ps7_init_tcl}")
        optional_lines.append("ps7_init")
        optional_lines.append("ps7_post_config")
        if fsbl_elf:
            optional_lines.append(f"dow {fsbl_elf}")
            optional_lines.append("con")
            optional_lines.append("after 2000")
            optional_lines.append("stop")
        optional_lines.append(f"dow {uboot_elf}")
        optional_lines.append("con")

        optional_block = "\n        ".join(optional_lines)

        tcl_script = f"""
        connect
        after 1000
        targets -set -filter {{name =~ "{a9_target_name}"}}
        after 500
        rst -system
        after 2000
        {optional_block}
        puts "U-Boot started via JTAG"
        """
        self.logger.debug(f"Zynq U-Boot bootstrap TCL:\n{tcl_script}")
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Zynq U-Boot bootstrap failed: {stderr}")
        self.logger.info("Zynq U-Boot bootstrap completed")
        self.logger.debug(f"Bootstrap output: {stdout}")

    @Driver.check_active
    @step()
    def load_and_run_elf(
        self,
        elf_path: str,
        a9_target_name: str = "*Cortex-A9 MPCore #0",
        bitstream_path: str | None = None,
        ps7_init_tcl: str | None = None,
    ) -> None:
        """JTAG-load and start an arbitrary bare-metal ELF (e.g. no-os firmware).

        Generalizes :meth:`load_zynq_uboot` to any ELF that runs directly on a
        Zynq core (no FSBL/U-Boot chain). The same xsdb sequence is used:
        ``connect → rst -system → [fpga] → [ps7_init] → dow elf → con``. The
        optional ``bitstream_path`` programs the PL first (required when the
        firmware touches FPGA-fabric peripherals), and ``ps7_init_tcl`` runs the
        board PS init — both are produced by the no-os build's HDL ``.xsa``.
        """
        self.logger.info(f"JTAG-loading bare-metal ELF from {elf_path}")

        lines = []
        if bitstream_path:
            lines.append(f"fpga -f {bitstream_path}")
            lines.append("after 2000")
        if ps7_init_tcl:
            lines.append(f"source {ps7_init_tcl}")
            lines.append("ps7_init")
            lines.append("ps7_post_config")
        lines.append(f"dow {elf_path}")
        lines.append("con")
        optional_block = "\n        ".join(lines)

        tcl_script = f"""
        connect
        after 1000
        targets -set -filter {{name =~ "{a9_target_name}"}}
        after 500
        rst -system
        after 2000
        {optional_block}
        puts "Bare-metal ELF started via JTAG"
        """
        self.logger.debug(f"ELF load TCL:\n{tcl_script}")
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Bare-metal ELF load failed: {stderr}")
        self.logger.info("Bare-metal ELF load completed")
        self.logger.debug(f"ELF load output: {stdout}")

    @Driver.check_active
    @step()
    def stop_zynq_cpu(self, a9_target_name: str = "*Cortex-A9 MPCore #0") -> None:
        """Halt the A9 #0 core — used between failed bootstrap attempts."""
        self.logger.info(f"Stopping Zynq A9 CPU ({a9_target_name})")
        tcl_script = f"""
        connect
        after 500
        targets -set -filter {{name =~ "{a9_target_name}"}}
        stop
        puts "A9 CPU stopped"
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            self.logger.warning(f"Stop CPU warning: {stderr}")
        self.logger.debug(f"Stop CPU output: {stdout}")
