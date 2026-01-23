"""Driver to program Xilinx FPGAs via JTAG using xsdb."""

import os

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.step import step


@target_factory.reg_driver
@attr.s(eq=False)
class XilinxJTAGDriver(Driver):
    """XilinxJTAGDriver - Driver to program Xilinx FPGAs via JTAG using xsdb.

    Supports Virtex, Artix, and Kintex FPGAs with Microblaze soft processors.
    Uses Xilinx xsdb (Xilinx Software Command-Line Tool) for JTAG operations.

    This driver implements the boot sequence for logic-only FPGAs:
    1. Flash bitstream to configure FPGA fabric and instantiate Microblaze
    2. Download Linux kernel image to Microblaze memory
    3. Start kernel execution
    4. Disconnect from JTAG

    Bindings:
        xilinxdevicejtag: XilinxDeviceJTAG resource for JTAG configuration
        xilinxvivado: XilinxVivadoTool resource for xsdb tool access
    """

    bindings = {
        "xilinxdevicejtag": {"XilinxDeviceJTAG"},
        "xilinxvivado": {"XilinxVivadoTool"},
    }

    def __attrs_post_init__(self):
        """Initialize driver and verify xsdb is available."""
        super().__attrs_post_init__()
        self.logger.info("XilinxJTAGDriver initialized")

        # Verify xsdb is executable
        if not os.path.exists(self.xilinxvivado.xsdb_path):
            raise ExecutionError(f"xsdb not found at {self.xilinxvivado.xsdb_path}")

        self.logger.debug(f"xsdb found at: {self.xilinxvivado.xsdb_path}")
        self.logger.debug(f"Vivado version: {self.xilinxvivado.version}")

    @Driver.check_active
    @step()
    def connect_jtag(self):
        """Connect to JTAG interface.

        Raises:
            ExecutionError: If JTAG connection fails.
        """
        self.logger.info("Connecting to JTAG")
        tcl_script = """
        connect
        after 1000
        puts "JTAG connected"
        """
        stdout, stderr, returncode = self.xilinxvivado.run_xsdb_script(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"JTAG connection failed: {stderr}")
        self.logger.debug(f"JTAG connection output: {stdout}")

    @Driver.check_active
    @step()
    def flash_bitstream(self):
        """Flash the FPGA bitstream via JTAG.

        Loads the bitstream file to configure the FPGA fabric and instantiate
        the Microblaze processor.

        Raises:
            ExecutionError: If flashing fails or bitstream file not found.
        """
        if not self.xilinxdevicejtag.bitstream_path:
            raise ExecutionError("Bitstream path not configured in XilinxDeviceJTAG resource")

        if not os.path.exists(self.xilinxdevicejtag.bitstream_path):
            raise ExecutionError(f"Bitstream file not found: {self.xilinxdevicejtag.bitstream_path}")

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

        stdout, stderr, returncode = self.xilinxvivado.run_xsdb_script(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Bitstream flash failed: {stderr}")

        self.logger.info("Bitstream flashed successfully")
        self.logger.debug(f"Flash output: {stdout}")

    @Driver.check_active
    @step()
    def download_kernel(self):
        """Download Linux kernel image to Microblaze processor.

        Uses xsdb 'dow' (download) command to load the kernel into Microblaze memory.
        The bitstream must be flashed before calling this method.

        Raises:
            ExecutionError: If download fails or kernel file not found.
        """
        if not self.xilinxdevicejtag.kernel_path:
            raise ExecutionError("Kernel path not configured in XilinxDeviceJTAG resource")

        if not os.path.exists(self.xilinxdevicejtag.kernel_path):
            raise ExecutionError(f"Kernel file not found: {self.xilinxdevicejtag.kernel_path}")

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

        stdout, stderr, returncode = self.xilinxvivado.run_xsdb_script(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Kernel download failed: {stderr}")

        self.logger.info("Kernel downloaded successfully")
        self.logger.debug(f"Download output: {stdout}")

    @Driver.check_active
    @step()
    def start_execution(self):
        """Start kernel execution on Microblaze processor.

        Uses xsdb 'con' (continue) command to begin kernel boot.
        The kernel must be downloaded before calling this method.

        Raises:
            ExecutionError: If execution start fails.
        """
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

        stdout, stderr, returncode = self.xilinxvivado.run_xsdb_script(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"Kernel execution failed: {stderr}")

        self.logger.info("Kernel execution started")
        self.logger.debug(f"Execution output: {stdout}")

    @Driver.check_active
    @step()
    def disconnect_jtag(self):
        """Disconnect from JTAG interface."""
        self.logger.info("Disconnecting from JTAG")
        tcl_script = """
        disconnect
        puts "JTAG disconnected"
        """
        stdout, stderr, returncode = self.xilinxvivado.run_xsdb_script(tcl_script)
        if returncode != 0:
            self.logger.warning(f"JTAG disconnect warning: {stderr}")
        self.logger.debug(f"JTAG disconnect output: {stdout}")
