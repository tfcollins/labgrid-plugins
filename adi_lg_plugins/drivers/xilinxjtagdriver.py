"""Driver to program Xilinx FPGAs via JTAG using xsdb.

Supports both local execution (test runner == exporter) and remote
execution (a client acquiring the place through a coordinator runs xsdb
on the exporter host). Remote detection and ssh are unified in
:class:`~adi_lg_plugins.drivers._remote.RemoteExecMixin`, keyed off the
bound ``xilinxdevicejtag`` resource: when it carries exporter-host info
(``host`` or ``extra['proxy']``), generated TCL and every input payload are
staged to the exporter and xsdb runs there over a reused ssh connection;
otherwise xsdb runs locally. Prefix a path with ``exporter:`` to explicitly
refer to a file which already exists on the xsdb host and skip staging.
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

_EXPORTER_PATH_PREFIX = "exporter:"
_TCL_BARE_PATH_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_./:+,@%=-"
)


def _tcl_quote_path(path: str) -> str:
    """Return one Tcl word which evaluates to ``path`` without substitutions."""
    if path and all(char in _TCL_BARE_PATH_CHARS for char in path):
        return path
    encoded = path.encode("utf-8").hex()
    return f"[encoding convertfrom utf-8 [binary decode hex {encoded}]]"


# ZynqMP CRL_APB.BOOT_MODE_USER (UG1087): [15:12] alt_boot_mode (rw), [8] use_alt
# (rw), [3:0] boot_mode (ro): the mode pins captured at POR, replaced by
# alt_boot_mode as soon as use_alt is set (so it is the mode the next system
# reset boots, not the pins). The override survives a system reset
# (``rst -system``) and is cleared by POR. BOOT_MODE_POR keeps the pins.
ZYNQMP_BOOT_MODE_USER = 0xFF5E0200
ZYNQMP_BOOT_MODE_POR = 0xFF5E0204
ZYNQMP_CSU_MULTI_BOOT = 0xFFCA0010
_USE_ALT = 0x100

# Boot mode pin encodings, UG1085 "Boot Modes" table.
ZYNQMP_BOOT_MODES = {
    "jtag": 0x0,
    "qspi24": 0x1,
    "qspi32": 0x2,
    "sd0": 0x3,
    "nand": 0x4,
    "sd1": 0x5,
    "emmc": 0x6,
    "usb0": 0x7,
    "pjtag0": 0x8,
    "pjtag1": 0x9,
    "sd1-ls": 0xE,
}
_BOOT_MODE_NAMES = {value: name for name, value in ZYNQMP_BOOT_MODES.items()}


def zynqmp_boot_mode_value(mode: str | int) -> int:
    """The 4-bit boot mode for a name in ``ZYNQMP_BOOT_MODES`` or a pin value."""
    if isinstance(mode, str):
        key = mode.strip().lower().replace("_", "-")
        if key in ZYNQMP_BOOT_MODES:
            return ZYNQMP_BOOT_MODES[key]
        try:
            mode = int(key, 0)
        except ValueError:
            raise ValueError(
                f"unknown ZynqMP boot mode {mode!r}; use one of "
                f"{', '.join(ZYNQMP_BOOT_MODES)} or a value 0x0-0xF"
            ) from None
    if isinstance(mode, bool) or not isinstance(mode, int) or not 0 <= mode <= 0xF:
        raise ValueError(f"ZynqMP boot mode must be 0x0-0xF, got {mode!r}")
    return mode


def zynqmp_boot_mode_name(value: int) -> str:
    return _BOOT_MODE_NAMES.get(value, f"0x{value:X}")


def decode_zynqmp_boot_mode_user(raw: int, por: int | None = None) -> dict:
    """Split a BOOT_MODE_USER read (and optionally BOOT_MODE_POR) into fields.

    ``effective`` is the mode the BootROM uses on the next system reset:
    ``alt_boot_mode`` when ``use_alt`` is set, otherwise the strapped pins
    (BOOT_MODE_USER[3:0] already reports exactly that). ``pins`` -- the boot
    mode switches -- comes from BOOT_MODE_POR[3:0] when ``por`` is given, and
    is otherwise only known while no override is set (``None`` if it is).
    """
    use_alt = bool(raw & _USE_ALT)
    alt = (raw >> 12) & 0xF
    effective = raw & 0xF
    if por is not None:
        pins = por & 0xF
    else:
        pins = None if use_alt else effective
    return {
        "raw": raw,
        "por": por,
        "pins": pins,
        "pins_name": zynqmp_boot_mode_name(pins) if pins is not None else None,
        "use_alt": use_alt,
        "alt_boot_mode": alt,
        "effective": effective,
        "effective_name": zynqmp_boot_mode_name(effective),
    }


@target_factory.reg_driver
@attr.s(eq=False)
class XilinxJTAGDriver(RemoteExecMixin, Driver):
    """Program Xilinx FPGAs via JTAG using xsdb.

    Bindings:

    * ``xilinxdevicejtag`` — ``XilinxDeviceJTAG`` resource containing JTAG
      target IDs and caller-local bitstream/kernel paths. Payloads are staged
      automatically; ``exporter:/path`` denotes a pre-existing exporter file.
    * ``xilinxvivado`` — ``XilinxVivadoTool`` resource containing
      ``vivado_path`` and ``xsdb_path``.
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

    def _stage_payload(self, path: str) -> str:
        """Return an xsdb-host path, staging caller-local files as needed.

        ``exporter:/path`` is the explicit compatibility form for a payload
        which already exists on the exporter. All other paths are made
        absolute on the caller before passing through ``_stage_file``.
        """
        path = os.fspath(path)
        if path.startswith(_EXPORTER_PATH_PREFIX):
            exporter_path = path.removeprefix(_EXPORTER_PATH_PREFIX)
            if not exporter_path:
                raise ValueError("exporter: payload path must not be empty")
            return exporter_path
        if self._is_remote and os.path.isabs(path) and not os.path.isfile(path):
            # Backward compatibility: before automatic staging, absolute paths
            # in exporter YAML were interpreted directly by exporter-side xsdb.
            return path
        return self._stage_file(os.path.abspath(path))

    def _stage_optional_payload(self, path: str | None) -> str | None:
        return self._stage_payload(path) if path else None

    def _run_xsdb(self, tcl_script: str, timeout: int = 300):
        """Execute ``tcl_script`` through xsdb, locally or on the exporter.

        The TCL script is staged to the host that runs xsdb (a no-op when
        local), then xsdb is invoked over the mixin's reused connection.

        Returns (stdout, stderr, returncode) as strings.
        """
        xsdb = self.xilinxvivado.xsdb_path

        if not tcl_script.strip().endswith("exit"):
            tcl_script = tcl_script.rstrip() + "\nexit\n"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".tcl", delete=False) as f:
            f.write(tcl_script)
            local_tcl = f.name

        try:
            remote_tcl = self._stage_file(local_tcl)
            result = subprocess.run(
                self._remote_prefix() + [xsdb, remote_tcl],
                stdin=subprocess.DEVNULL,
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
            self._cleanup_remote_stage()

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

        bitstream_path = self._stage_payload(self.xilinxdevicejtag.bitstream_path)
        self.logger.info(f"Flashing bitstream: {self.xilinxdevicejtag.bitstream_path}")

        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.root_target}
        after 1000
        fpga -f {_tcl_quote_path(bitstream_path)}
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

        kernel_path = self._stage_payload(self.xilinxdevicejtag.kernel_path)
        self.logger.info(f"Downloading kernel: {self.xilinxdevicejtag.kernel_path}")

        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.microblaze_target}
        after 1000
        dow {_tcl_quote_path(kernel_path)}
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
        bitstream_path = self._stage_payload(self.xilinxdevicejtag.bitstream_path)
        kernel_path = self._stage_payload(self.xilinxdevicejtag.kernel_path)
        tcl_script = f"""
        connect
        after 1000
        targets {self.xilinxdevicejtag.root_target}
        after 1000
        fpga -f {_tcl_quote_path(bitstream_path)}
        after 2000
        targets {self.xilinxdevicejtag.microblaze_target}
        after 1000
        dow {_tcl_quote_path(kernel_path)}
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
        ps7_init_tcl = self._stage_payload(ps7_init_tcl)
        uboot_elf = self._stage_payload(uboot_elf)
        bitstream_path = self._stage_optional_payload(bitstream_path)
        fsbl_elf = self._stage_optional_payload(fsbl_elf)
        self.logger.info(f"JTAG-bootstrapping Zynq-7000 U-Boot from {uboot_elf}")

        optional_lines = []
        if bitstream_path:
            optional_lines.append(f"fpga -f {_tcl_quote_path(bitstream_path)}")
            optional_lines.append("after 2000")
        optional_lines.append(f"source {_tcl_quote_path(ps7_init_tcl)}")
        optional_lines.append("ps7_init")
        optional_lines.append("ps7_post_config")
        if fsbl_elf:
            optional_lines.append(f"dow {_tcl_quote_path(fsbl_elf)}")
            optional_lines.append("con")
            optional_lines.append("after 2000")
            optional_lines.append("stop")
        optional_lines.append(f"dow {_tcl_quote_path(uboot_elf)}")
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

        Caller paths are resolved to absolute and staged to the xsdb host.
        Use the ``exporter:`` prefix for explicit pre-existing exporter files.
        """
        elf_path = self._stage_payload(elf_path)
        bitstream_path = self._stage_optional_payload(bitstream_path)
        ps7_init_tcl = self._stage_optional_payload(ps7_init_tcl)
        self.logger.info(f"JTAG-loading bare-metal ELF from {elf_path}")

        lines = []
        if bitstream_path:
            lines.append(f"fpga -f {_tcl_quote_path(bitstream_path)}")
            lines.append("after 2000")
        if ps7_init_tcl:
            lines.append(f"source {_tcl_quote_path(ps7_init_tcl)}")
            lines.append("ps7_init")
            lines.append("ps7_post_config")
        lines.append(f"dow {_tcl_quote_path(elf_path)}")
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
            psu_init_tcl: Caller-local board ``psu_init.tcl`` (staged automatically).
            spl_elf: Caller-local ``spl/u-boot-spl`` (staged automatically).
            bitstream_path: Optional PL bitstream to program before psu_init.
            a53_target_name: xsdb target filter for the boot A53 core.
            apu_release_rst_value: value written to ``0xFD1A0104`` to release
                the APU. Use ``0x0`` to release all four A53s (can destabilise
                later debug); prefer the board's generated per-core value.
            dcc_log_path: Optional output path on the xsdb host. Outputs are
                not copied back to the caller. Leave ``None`` to skip capture.
            settle_ms: milliseconds to let the SPL run before stopping DCC
                capture / returning.
        """
        psu_init_tcl = self._stage_payload(psu_init_tcl)
        spl_elf = self._stage_payload(spl_elf)
        bitstream_path = self._stage_optional_payload(bitstream_path)
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
            lines.append(f"fpga -file {_tcl_quote_path(bitstream_path)}")
            lines.append("after 500")
            lines.append('targets -set -nocase -filter {name =~ "PSU"}')
        lines += [
            f"source {_tcl_quote_path(psu_init_tcl)}",
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
            f"dow {_tcl_quote_path(spl_elf)}",
        ]
        if dcc_log_path:
            lines.append(
                f"catch {{readjtaguart -start -handle [open {_tcl_quote_path(dcc_log_path)} w]}}"
            )
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
        psu_init_tcl = self._stage_payload(psu_init_tcl)
        pmufw_bin = self._stage_payload(pmufw_bin)
        uboot_bin = self._stage_payload(uboot_bin)
        handoff_bin = self._stage_optional_payload(handoff_bin)
        bitstream_path = self._stage_optional_payload(bitstream_path)
        ddr_scrub_elf = self._stage_optional_payload(ddr_scrub_elf)
        bl31_bin = self._stage_optional_payload(bl31_bin)
        atf_handoff_bin = self._stage_optional_payload(atf_handoff_bin)
        pm_config_bin = self._stage_optional_payload(pm_config_bin)
        poll_count = max(1, int(pmufw_timeout_ms) // 100)

        lines = [
            f"connect -url {jtag_url}",
            "after 1000",
            "configparams force-mem-accesses 1",
            'targets -set -nocase -filter {name =~ "PSU"}',
            "mwr 0xffff0000 0x14000000",
            f"mwr 0xFD1A0104 {apu_release_rst_value}",
            "after 1000",
            f"source {_tcl_quote_path(psu_init_tcl)}",
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
                f"dow {_tcl_quote_path(ddr_scrub_elf)}",
                "con",
                f"after {int(ddr_scrub_settle_ms)}",
                "catch {stop}",
                f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
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
            f"dow -force -data {_tcl_quote_path(pmufw_bin)} {pmufw_address}",
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
            lines.append(f"dow -force -data {_tcl_quote_path(pm_config_bin)} {pm_config_address}")

        if bitstream_path:
            lines += [
                'targets -set -filter {name == "PL"}',
                f"fpga -file {_tcl_quote_path(bitstream_path)}",
                'puts "FPGA_STATE=[fpga -state]"',
                'targets -set -nocase -filter {name =~ "PSU"}',
                "psu_post_config",
                "psu_ps_pl_reset_config",
                "psu_ps_pl_isolation_removal",
            ]

        lines += [
            'targets -set -nocase -filter {name =~ "PSU"}',
            f"dow -force -data {_tcl_quote_path(uboot_bin)} {uboot_address}",
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
                f"dow -force -data {_tcl_quote_path(bl31_bin)} {bl31_address}",
                f"dow -force -data {_tcl_quote_path(atf_handoff_bin)} {handoff_address}",
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
                f"dow -force -data {_tcl_quote_path(handoff_bin)} {handoff_address}",
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
        psu_init_tcl = self._stage_payload(psu_init_tcl)
        trampoline_elf = self._stage_payload(trampoline_elf)
        kernel_image = self._stage_payload(kernel_image)
        initramfs = self._stage_payload(initramfs)
        dtb = self._stage_payload(dtb)
        ddr_scrub_elf = self._stage_optional_payload(ddr_scrub_elf)
        bitstream_path = self._stage_optional_payload(bitstream_path)
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
                f"fpga -file {_tcl_quote_path(bitstream_path)}",
                'puts "RECOVERY_FPGA_STATE=[fpga -state]"',
                'targets -set -nocase -filter {name =~ "PSU"}',
            ]
        lines += [
            f"source {_tcl_quote_path(psu_init_tcl)}",
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
                f"dow {_tcl_quote_path(ddr_scrub_elf)}",
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
            f"dow -force -data {_tcl_quote_path(kernel_image)} {kernel_address}",
            f"dow -force -data {_tcl_quote_path(initramfs)} {initramfs_address}",
            f"dow -force -data {_tcl_quote_path(dtb)} {dtb_address}",
            f'targets -set -nocase -filter {{name =~ "{a53_target_name}"}}',
            "catch {stop}",
            "rst -processor -clear-registers",
            f"dow {_tcl_quote_path(trampoline_elf)}",
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

    def _zynqmp_psu_preamble(self, jtag_url: str) -> list[str]:
        return [
            f"connect -url {jtag_url}",
            "after 500",
            "configparams force-mem-accesses 1",
            'targets -set -nocase -filter {name =~ "PSU"}',
        ]

    @staticmethod
    def _boot_mode_report() -> str:
        return (
            'puts [format "BOOT_MODE_USER=0x%08x BOOT_MODE_POR=0x%08x" '
            f"[mrd -force -value {ZYNQMP_BOOT_MODE_USER:#x}] "
            f"[mrd -force -value {ZYNQMP_BOOT_MODE_POR:#x}]]"
        )

    @staticmethod
    def _parse_boot_mode_marker(stdout: str) -> dict | None:
        """The last BOOT_MODE_USER/BOOT_MODE_POR report xsdb printed, decoded."""
        info = None
        for line in stdout.splitlines():
            fields = dict(
                part.split("=", 1) for part in line.split() if part.startswith("BOOT_MODE_")
            )
            if "BOOT_MODE_USER" in fields:
                por = fields.get("BOOT_MODE_POR")
                info = decode_zynqmp_boot_mode_user(
                    int(fields["BOOT_MODE_USER"], 16), int(por, 16) if por else None
                )
        return info

    @Driver.check_active
    @step()
    def get_zynqmp_boot_mode(self, jtag_url: str = "TCP:127.0.0.1:3121") -> dict:
        """Read ``CRL_APB.BOOT_MODE_USER`` (``0xFF5E0200``) of a ZynqMP over JTAG.

        Returns the fields from :func:`decode_zynqmp_boot_mode_user`: the
        boot mode switches (``pins``, from ``BOOT_MODE_POR``), whether a
        software override (``use_alt``) is set, the override value, and the
        ``effective`` mode the next system reset boots from. The board must be
        powered.
        """
        lines = self._zynqmp_psu_preamble(jtag_url) + [
            self._boot_mode_report(),
            "disconnect",
        ]
        stdout, stderr, returncode = self._run_xsdb("\n".join(lines) + "\n", timeout=120)
        info = self._parse_boot_mode_marker(stdout)
        if returncode != 0 or info is None:
            raise ExecutionError(f"Reading ZynqMP BOOT_MODE_USER failed: {stderr or stdout}")
        self.logger.info(
            "ZynqMP boot mode: switches=%s override=%s -> next reset boots %s "
            "(BOOT_MODE_USER=0x%08x)",
            info["pins_name"],
            zynqmp_boot_mode_name(info["alt_boot_mode"]) if info["use_alt"] else "none",
            info["effective_name"],
            info["raw"],
        )
        return info

    @Driver.check_active
    @step()
    def set_zynqmp_boot_mode(
        self,
        mode: str | int,
        reset: bool = True,
        clear_multiboot: bool = True,
        jtag_url: str = "TCP:127.0.0.1:3121",
    ) -> dict:
        """Override a ZynqMP's boot mode pins over JTAG, then (by default) reboot.

        Writes ``(mode << 12) | 0x100`` to ``CRL_APB.BOOT_MODE_USER``
        (``0xFF5E0200``): ``alt_boot_mode`` = ``mode`` with ``use_alt`` set.
        The BootROM reads it on the next **system reset**, so with
        ``reset=True`` this issues ``rst -system`` and the board boots from
        ``mode`` without touching its switches -- e.g. ``"sd1-ls"`` boots the
        SD card of a board strapped for JTAG, and ``"jtag"`` stops a board
        strapped for SD at the BootROM so it can be JTAG-booted without racing
        the card.

        The override survives later system resets and lasts until a power-on
        reset (a power cycle) or :meth:`clear_zynqmp_boot_mode_override`.

        Args:
            mode: a name from ``ZYNQMP_BOOT_MODES`` (``jtag``, ``qspi24``,
                ``qspi32``, ``sd0``, ``nand``, ``sd1``, ``emmc``, ``usb0``,
                ``pjtag0``, ``pjtag1``, ``sd1-ls``) or a 4-bit pin value.
            reset: issue ``rst -system`` after the write. Without it the new
                mode only takes effect at the next system reset.
            clear_multiboot: zero ``CSU_MULTI_BOOT`` (``0xFFCA0010``) first so
                the BootROM starts its image search at ``BOOT.BIN`` rather than
                a ``BOOT000N.BIN`` left by an earlier fallback.
            jtag_url: hw_server URL as seen from the host running xsdb.

        Returns:
            The decoded register read back after the write (before the reset).
        """
        value = zynqmp_boot_mode_value(mode)
        word = (value << 12) | _USE_ALT
        name = zynqmp_boot_mode_name(value)
        self.logger.info(
            "Setting ZynqMP boot mode to %s (BOOT_MODE_USER=0x%04x)%s",
            name,
            word,
            ", then system reset" if reset else "",
        )
        lines = self._zynqmp_psu_preamble(jtag_url) + ["catch {stop}"]
        if clear_multiboot:
            lines.append(f"mwr -force {ZYNQMP_CSU_MULTI_BOOT:#x} 0x0")
        lines += [
            f"mwr -force {ZYNQMP_BOOT_MODE_USER:#x} {word:#06x}",
            self._boot_mode_report(),
        ]
        if reset:
            # The debugger must not hold the cores after the reset, or the
            # BootROM's hand-off to the FSBL is caught instead of run.
            lines += ["rst -system", "after 500", "catch {con}"]
        lines.append("disconnect")
        stdout, stderr, returncode = self._run_xsdb("\n".join(lines) + "\n", timeout=120)
        info = self._parse_boot_mode_marker(stdout)
        if returncode != 0 or info is None:
            raise ExecutionError(f"Setting ZynqMP boot mode failed: {stderr or stdout}")
        if not info["use_alt"] or info["alt_boot_mode"] != value:
            raise ExecutionError(
                f"BOOT_MODE_USER read back 0x{info['raw']:08x} after writing 0x{word:04x}; "
                "the override did not take"
            )
        return info

    @Driver.check_active
    @step()
    def clear_zynqmp_boot_mode_override(
        self, reset: bool = False, jtag_url: str = "TCP:127.0.0.1:3121"
    ) -> dict:
        """Clear the ``BOOT_MODE_USER`` override so the boot mode pins apply again.

        A power cycle does the same. With ``reset=True`` the board is system-reset
        and boots per its switches.
        """
        self.logger.info("Clearing ZynqMP boot mode override")
        lines = self._zynqmp_psu_preamble(jtag_url) + [
            f"mwr -force {ZYNQMP_BOOT_MODE_USER:#x} 0x0",
            self._boot_mode_report(),
        ]
        if reset:
            lines += ["rst -system", "after 500", "catch {con}"]
        lines.append("disconnect")
        stdout, stderr, returncode = self._run_xsdb("\n".join(lines) + "\n", timeout=120)
        info = self._parse_boot_mode_marker(stdout)
        if returncode != 0 or info is None:
            raise ExecutionError(f"Clearing ZynqMP boot mode override failed: {stderr or stdout}")
        if info["use_alt"]:
            raise ExecutionError(f"BOOT_MODE_USER still has use_alt set (0x{info['raw']:08x})")
        return info

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
