"""Driver to program Xilinx FPGAs via JTAG using xsdb.

Supports both local execution (test runner == exporter) and remote
execution (a client acquiring the place through a coordinator runs xsdb
on the exporter host). Remote detection and ssh are unified in
:class:`~adi_lg_plugins.drivers._remote.RemoteExecMixin`, keyed off the
bound ``xilinxdevicejtag`` resource: when it carries exporter-host info
(``host`` or ``extra['proxy']``), the generated TCL script is staged to
the exporter and xsdb runs there over a single reused ssh connection;
otherwise xsdb runs locally.

Note: bitstream / kernel / ELF / ps7_init paths embedded in the TCL are
"as seen by the host that runs xsdb" — they are assumed to already exist
on the exporter and are NOT auto-staged by this driver.
"""

import os
import subprocess
import tempfile

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.step import step

from ._remote import RemoteExecMixin


@target_factory.reg_driver
@attr.s(eq=False)
class XilinxJTAGDriver(RemoteExecMixin, Driver):
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

    # RemoteExecMixin: the resource that locates the exporter host.
    _remote_binding = "xilinxdevicejtag"

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("XilinxJTAGDriver initialized")
        self.logger.debug(f"xsdb path: {self.xilinxvivado.xsdb_path}")

    def _exporter_host(self, res):
        if os.environ.get("LG_FORCE_LOCAL_XSDB", "").lower() in ("1", "true", "yes", "on"):
            return None
        return super()._exporter_host(res)

    def _run_xsdb(self, tcl_script: str):
        """Execute ``tcl_script`` through xsdb, locally or on the exporter.

        The TCL script is staged to the host that runs xsdb (a no-op when
        local), then xsdb is invoked over the mixin's reused connection.

        Returns (stdout, stderr, returncode) as strings.
        """
        xsdb = self.xilinxvivado.xsdb_path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
            f.write(tcl_script)
            local_tcl = f.name

        try:
            remote_tcl = self._stage_file(local_tcl)
            result = subprocess.run(
                self._remote_prefix() + [xsdb, remote_tcl],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return result.stdout, result.stderr, result.returncode
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

        Paths are resolved to absolute before being embedded in the xsdb TCL:
        xsdb runs the script from its own working directory (not the caller's),
        so a relative ``dow``/``fpga -f`` path would fail to open.
        """
        elf_path = os.path.abspath(elf_path)
        if bitstream_path:
            bitstream_path = os.path.abspath(bitstream_path)
        if ps7_init_tcl:
            ps7_init_tcl = os.path.abspath(ps7_init_tcl)
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

    @Driver.check_active
    @step()
    def load_zynqmp_uboot(
        self,
        psu_init_tcl: str,
        spl_elf: str,
        bitstream_path: str | None = None,
        a53_target_name: str = "*Cortex-A53*#0*",
        apu_release_rst_value: str = "0x380E",
        dcc_log_path: str | None = None,
        settle_ms: int = 12000,
    ) -> None:
        """JTAG-bootstrap Xilinx "mini" U-Boot SPL on a ZynqMP (UltraScale+).

        This is the UltraScale+ counterpart of :meth:`load_zynq_uboot`. It is
        required because ZynqMP differs fundamentally from Zynq-7000:

        * In **JTAG boot mode** (``BOOT_MODE_USER == 0x0``) the BootROM does
          not load PMU firmware and the MicroBlaze PMU is not a debug target,
          so full U-Boot + Arm Trusted Firmware (BL31) cannot run -- BL31
          spins forever in ``ipi_mb_notify`` waiting on the PMU IPI mailbox.
        * The working recovery bootstrap is the Xilinx ``xilinx_zynqmp_mini_*``
          SPL, which runs standalone in OCM at EL3 (no ATF, no PMU-FW) and
          exposes an ARM DCC / JTAG-UART console readable directly with xsdb.

        Sequence (proven on ADRV9009-ZU11EG / ADRV2CRR-FMC):

        1. Release the APU from reset without PMU-FW: write an AArch64
           ``b .`` bootloop to RVBAR (OCM ``0xFFFF0000``) then poke
           ``CRF_APB.RST_FPD_APU`` (``0xFD1A0104``). ``apu_release_rst_value``
           defaults to ``0x380E`` which releases A53 #0 while holding
           A53 #1..3 and L2 in reset -- matching the generated ZU11EG flow.
        2. (Optional) program the PL bitstream.
        3. ``source`` the board's generated ``psu_init.tcl`` and run
           ``psu_init``/``psu_post_config``/``psu_ps_pl_reset_config``/
           ``psu_ps_pl_isolation_removal`` to bring up clocks, DDR and the
           SD MIO mux. The psu_init path yields a clean core + DDR; an FSBL +
           ``rst -processor`` path breaks debugger DDR access (EDITR timeout).
        4. Clean the A53 (``rst -processor -clear-registers``), ``dow`` the
           SPL ELF and ``con``.
        5. If ``dcc_log_path`` is given, capture the DCC console to that file
           on the xsdb host via ``readjtaguart`` (headless; ``jtagterminal``
           needs an X server and is avoided).

        Args:
            psu_init_tcl: Path (on the xsdb host) to the board ``psu_init.tcl``.
            spl_elf: Path (on the xsdb host) to ``spl/u-boot-spl`` (mini SPL).
            bitstream_path: Optional PL bitstream to program before psu_init.
            a53_target_name: xsdb target filter for the boot A53 core.
            apu_release_rst_value: value written to ``0xFD1A0104`` to release
                the APU. Use ``0x0`` to release all four A53s (can destabilise
                later debug); prefer the board's generated per-core value.
            dcc_log_path: Optional path on the xsdb host to capture the DCC
                console log. Leave ``None`` to skip console capture.
            settle_ms: milliseconds to let the SPL run before stopping DCC
                capture / returning.
        """
        self.logger.info(f"JTAG-bootstrapping ZynqMP mini U-Boot SPL from {spl_elf}")

        lines = [
            "connect -url TCP:127.0.0.1:3121",
            "after 1000",
            "configparams force-mem-accesses 1",
            'targets -set -nocase -filter {name =~ "PSU"}',
            "mwr 0xffff0000 0x14000000",
            f"mwr 0xFD1A0104 {apu_release_rst_value}",
            "after 1000",
        ]
        if bitstream_path:
            lines.append(f"fpga -file {bitstream_path}")
            lines.append("after 500")
            lines.append('targets -set -nocase -filter {name =~ "PSU"}')
        lines += [
            f"source {psu_init_tcl}",
            "psu_init",
            "psu_post_config",
            "psu_ps_pl_reset_config",
            "psu_ps_pl_isolation_removal",
            "after 1500",
            f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
            "catch {stop}",
            "rst -processor -clear-registers",
            "after 1000",
            "catch {stop}",
            f"dow {spl_elf}",
        ]
        if dcc_log_path:
            lines.append(f"catch {{readjtaguart -start -handle [open {dcc_log_path} w]}}")
        lines.append("con")
        lines.append('puts "ZynqMP mini U-Boot SPL launched via JTAG"')
        lines.append(f"after {int(settle_ms)}")
        if dcc_log_path:
            lines.append("catch {readjtaguart -stop}")
        lines.append("disconnect")

        tcl_script = "\n        ".join(lines)
        tcl_script = f"\n        {tcl_script}\n        "
        self.logger.debug(f"ZynqMP SPL bootstrap TCL:\n{tcl_script}")
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            raise ExecutionError(f"ZynqMP mini U-Boot bootstrap failed: {stderr}")
        self.logger.info("ZynqMP mini U-Boot bootstrap completed")
        self.logger.debug(f"Bootstrap output: {stdout}")

    @Driver.check_active
    @step()
    def stop_zynqmp_cpu(self, a53_target_name: str = "*Cortex-A53*#0*") -> None:
        """Halt the ZynqMP A53 #0 core -- used between failed bootstrap attempts."""
        self.logger.info(f"Stopping ZynqMP A53 CPU ({a53_target_name})")
        tcl_script = f"""
        connect -url TCP:127.0.0.1:3121
        after 500
        targets -set -nocase -filter {{name =~ "{a53_target_name}"}}
        catch {{stop}}
        puts "A53 CPU stopped"
        disconnect
        """
        stdout, stderr, returncode = self._run_xsdb(tcl_script)
        if returncode != 0:
            self.logger.warning(f"Stop CPU warning: {stderr}")
        self.logger.debug(f"Stop CPU output: {stdout}")
