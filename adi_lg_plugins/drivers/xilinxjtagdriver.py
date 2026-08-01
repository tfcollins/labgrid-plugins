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

    def _run_xsdb(self, tcl_script: str, timeout: int = 300):
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
                timeout=timeout,
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
        jtag_url: str = "TCP:127.0.0.1:3121",
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
            f"connect -url {jtag_url}",
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
    def load_zynqmp_production_uboot(
        self,
        psu_init_tcl: str,
        pmufw_bin: str,
        uboot_bin: str,
        handoff_bin: str | None = None,
        bitstream_path: str | None = None,
        ddr_scrub_elf: str | None = None,
        bl31_bin: str | None = None,
        atf_handoff_bin: str | None = None,
        pm_config_bin: str | None = None,
        bl31_console_uart_base: str | None = None,
        bl31_console_ref_ctrl_address: str | None = None,
        bl31_console_reset_mask: str = "0x2",
        a53_target_name: str = "*Cortex-A53*#0*",
        apu_release_rst_value: str = "0x380E",
        pmufw_address: str = "0xFFDC0000",
        uboot_address: str = "0x08000000",
        handoff_address: str = "0x00100000",
        bl31_address: str = "0xFFFEA000",
        pm_config_address: str = "0x00200000",
        pmufw_timeout_ms: int = 10000,
        ddr_scrub_settle_ms: int = 30000,
        settle_ms: int = 12000,
        jtag_url: str = "TCP:127.0.0.1:3121",
    ) -> None:
        """Start production U-Boot on a ZynqMP board strapped for JTAG boot.

        This path is for a recovered SD card whose board cannot leave physical
        JTAG boot mode remotely. It reconstructs the parts of the production
        BootROM/FSBL chain which full U-Boot needs:

        * initialize the PS and DDR with the board's generated ``psu_init``;
        * optionally run an OCM-resident DDR ECC scrub before U-Boot relocates;
        * load PMU firmware through the physical PSU/DAP target, wake the PMU
          ROM, and require firmware to claim ``FW_IS_PRESENT``;
        * optionally program a production PL bitstream already converted to
          the byte order expected by xsdb;
        * physically load raw U-Boot and EL3-to-EL2 handoff binaries, reset the
          A53 translation state, and enter the handoff at EL3.

        For production U-Boot builds which issue SMC calls, pass ``bl31_bin``
        and ``atf_handoff_bin``. BL31 remains resident at EL3 and provides the
        Xilinx PM runtime services before entering U-Boot at EL2. For simpler
        U-Boot builds with no EL3 runtime dependency, ``handoff_bin`` may be a
        raw one-way EL3-to-EL2 trampoline instead.

        Loading every final payload through the PSU target avoids MMU
        translation faults left by a previous Linux or BL31 session.

        PMU ``FW_IS_PRESENT`` is a firmware-owned readiness indication. This
        method deliberately sets only ``DONT_SLEEP`` and fails if firmware does
        not assert readiness before the timeout.
        """
        self.logger.info(f"JTAG-starting production ZynqMP U-Boot from {uboot_bin}")

        use_bl31 = bl31_bin is not None or atf_handoff_bin is not None
        if use_bl31 and not (bl31_bin and atf_handoff_bin):
            raise ExecutionError("bl31_bin and atf_handoff_bin must be supplied together")
        if not use_bl31 and not handoff_bin:
            raise ExecutionError("either BL31 artifacts or handoff_bin are required")
        poll_count = max(1, int(pmufw_timeout_ms) // 100)

        lines = [
            f"connect -url {jtag_url}",
            "after 1000",
            "configparams force-mem-accesses 1",
            'targets -set -nocase -filter {name =~ "PSU"}',
            "mwr 0xffff0000 0x14000000",
            f"mwr 0xFD1A0104 {apu_release_rst_value}",
            "after 1000",
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
        ]

        if ddr_scrub_elf:
            lines += [
                f"dow {ddr_scrub_elf}",
                "con",
                f"after {int(ddr_scrub_settle_ms)}",
                "stop",
                'puts "DDR_ECC_SCRUB_COMPLETE pc=[rrd pc]"',
                "rst -processor -clear-registers",
                "after 1000",
                "catch {stop}",
            ]

        lines += [
            'targets -set -nocase -filter {name =~ "PSU"}',
            "set pmu_control_addr 0xFFD80000",
            "set pmu_sleep 0",
            f"for {{set i 0}} {{$i < {poll_count}}} {{incr i}} {{",
            "    set pmu_control [mrd -force -value $pmu_control_addr]",
            "    if {($pmu_control & 0x10000) != 0} {set pmu_sleep 1; break}",
            "    after 100",
            "}",
            'if {!$pmu_sleep} {error "PMU ROM did not enter sleep"}',
            f"dow -force -data {pmufw_bin} {pmufw_address}",
            "set pmu_control [mrd -force -value $pmu_control_addr]",
            "mwr $pmu_control_addr [expr {$pmu_control | 0x1}]",
            "set pmufw_ready 0",
            f"for {{set i 0}} {{$i < {poll_count}}} {{incr i}} {{",
            "    after 100",
            "    set pmu_control [mrd -force -value $pmu_control_addr]",
            "    if {($pmu_control & 0x10) != 0} {set pmufw_ready 1; break}",
            "}",
            'if {!$pmufw_ready} {error "PMU firmware did not claim FW_IS_PRESENT"}',
            'puts [format "PMUFW_READY control=0x%08x" $pmu_control]',
        ]

        if pm_config_bin:
            lines.append(f"dow -force -data {pm_config_bin} {pm_config_address}")

        if bitstream_path:
            lines += [
                'targets -set -filter {name == "PL"}',
                f"fpga -file {bitstream_path}",
                'puts "FPGA_STATE=[fpga -state]"',
            ]

        lines += [
            'targets -set -nocase -filter {name =~ "PSU"}',
            f"dow -force -data {uboot_bin} {uboot_address}",
        ]

        if use_bl31:
            if bool(bl31_console_uart_base) != bool(bl31_console_ref_ctrl_address):
                raise ExecutionError(
                    "BL31 console UART base and reference-clock address must be supplied together"
                )
            if bl31_console_uart_base:
                lines += [
                    f"mwr {bl31_console_ref_ctrl_address} 0x01010F00",
                    "set iou_rst [lindex [mrd -value -force 0xFF5E0238] 0]",
                    f"mwr 0xFF5E0238 [expr {{$iou_rst & ~{bl31_console_reset_mask}}}]",
                    f"mwr [expr {{{bl31_console_uart_base} + 0x34}}] 0x00000006",
                    f"mwr [expr {{{bl31_console_uart_base} + 0x18}}] 0x0000007C",
                    f"mwr [expr {{{bl31_console_uart_base} + 0x04}}] 0x00000020",
                    f"mwr {bl31_console_uart_base} 0x00000114",
                ]
            lines += [
                f"dow -force -data {bl31_bin} {bl31_address}",
                f"dow -force -data {atf_handoff_bin} {handoff_address}",
                f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
                "catch {stop}",
                f"rwr r0 {handoff_address}",
                "rwr r1 0",
                "rwr r2 0",
                "rwr r3 0",
                f"rwr pc {bl31_address}",
                "con",
                'puts "PRODUCTION_BL31_LAUNCHED"',
            ]
        else:
            lines += [
                f"dow -force -data {handoff_bin} {handoff_address}",
                f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
                "catch {stop}",
                f"rwr pc {handoff_address}",
                "con",
                'puts "PRODUCTION_UBOOT_LAUNCHED"',
            ]
        lines += [f"after {int(settle_ms)}", "disconnect"]

        tcl_script = "\n        ".join(lines)
        tcl_script = f"\n        {tcl_script}\n        "
        self.logger.debug(f"ZynqMP production U-Boot handoff TCL:\n{tcl_script}")
        xsdb_timeout = max(300, int(ddr_scrub_settle_ms / 1000) + 300)
        stdout, stderr, returncode = self._run_xsdb(tcl_script, timeout=xsdb_timeout)
        if returncode != 0:
            detail = stderr or stdout
            raise ExecutionError(f"ZynqMP production U-Boot handoff failed: {detail}")
        self.logger.info("ZynqMP production U-Boot handoff completed")
        self.logger.debug(f"Production handoff output: {stdout}")

    @Driver.check_active
    @step()
    def load_zynqmp_recovery_linux(
        self,
        psu_init_tcl: str,
        trampoline_elf: str,
        kernel_image: str,
        initramfs: str,
        dtb: str,
        ddr_scrub_elf: str | None = None,
        bitstream_path: str | None = None,
        a53_target_name: str = "*Cortex-A53*#0*",
        apu_release_rst_value: str = "0x380E",
        trampoline_address: str = "0x00100000",
        kernel_address: str = "0x00200000",
        initramfs_address: str = "0x10000000",
        dtb_address: str = "0x20000000",
        ddr_scrub_done_address: str | None = None,
        ddr_scrub_settle_ms: int = 120000,
        post_init_mask_writes: list | None = None,
        settle_ms: int = 3000,
        jtag_url: str = "TCP:127.0.0.1:3121",
    ) -> None:
        """JTAG-load a RAM-rooted ZynqMP recovery Linux without BL31 or PMUFW.

        Kernel, initramfs and DTB are downloaded through the physical PSU/DAP
        target, so stale A53 translation state cannot redirect writes. The
        caller-provided EL3 trampoline performs the board-specific timer/GIC
        setup and enters Linux at non-secure EL2.
        """
        lines = [
            f"connect -url {jtag_url}",
            "after 1000",
            "configparams force-mem-accesses 1",
            'targets -set -nocase -filter {name =~ "PSU"}',
            "mwr 0xffff0000 0x14000000",
            f"mwr 0xFD1A0104 {apu_release_rst_value}",
        ]
        if bitstream_path:
            lines += [
                f"fpga -file {bitstream_path}",
                'puts "RECOVERY_FPGA_STATE=[fpga -state]"',
                'targets -set -nocase -filter {name =~ "PSU"}',
            ]
        lines += [
            f"source {psu_init_tcl}",
            "psu_init",
            "psu_post_config",
            "psu_ps_pl_reset_config",
            "psu_ps_pl_isolation_removal",
        ]
        for address, mask, value in post_init_mask_writes or []:
            lines.append(f"mask_write {address} {mask} {value}")
        lines.append("after 1500")
        lines += [
            f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
            "catch {stop}",
            "rst -processor -clear-registers",
            "after 1000",
            "catch {stop}",
        ]
        if ddr_scrub_elf:
            lines += [
                f"dow {ddr_scrub_elf}",
                "con",
                f"after {int(ddr_scrub_settle_ms)}",
                "stop",
            ]
            if ddr_scrub_done_address:
                lines += [
                    "set scrub_pc_text [lindex [rrd pc] 1]",
                    "scan $scrub_pc_text %llx scrub_pc",
                    f"set scrub_done [expr {{{ddr_scrub_done_address}}}]",
                    'if {$scrub_pc != $scrub_done && $scrub_pc != ($scrub_done + 4)} {error "DDR ECC scrub did not reach completion loop: $scrub_pc"}',
                ]
            lines += [
                'puts "RECOVERY_DDR_ECC_SCRUB_COMPLETE pc=[rrd pc]"',
                "rst -processor -clear-registers",
                "after 1000",
                "catch {stop}",
            ]
        lines += [
            'targets -set -nocase -filter {name =~ "PSU"}',
            f"dow -force -data {kernel_image} {kernel_address}",
            f"dow -force -data {initramfs} {initramfs_address}",
            f"dow -force -data {dtb} {dtb_address}",
            f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
            "catch {stop}",
            "rst -processor -clear-registers",
            f"dow {trampoline_elf}",
            f"rwr pc {trampoline_address}",
            "con",
            'puts "RECOVERY_LINUX_LAUNCHED"',
            f"after {int(settle_ms)}",
            "disconnect",
        ]
        tcl_script = "\n        ".join(lines)
        tcl_script = f"\n        {tcl_script}\n        "
        self.logger.debug(f"ZynqMP recovery Linux TCL:\n{tcl_script}")
        xsdb_timeout = max(300, int(ddr_scrub_settle_ms / 1000) + 300)
        stdout, stderr, returncode = self._run_xsdb(tcl_script, timeout=xsdb_timeout)
        if returncode != 0:
            raise ExecutionError(f"ZynqMP recovery Linux launch failed: {stderr or stdout}")
        self.logger.info("ZynqMP recovery Linux launched via JTAG")

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
