import enum
import os
import shutil
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for TFTP-based boot."""

    unknown = 0
    powered_off = 1
    update_boot_files = 2
    booting = 3
    # Optional JTAG-bootstrap step (xsdb-loads ps7_init + bitstream +
    # FSBL + U-Boot ELF into DDR) so the strategy works on SDs that
    # don't carry a working FSBL/U-Boot. Falls through to booting when
    # the JTAG bindings/inputs aren't supplied — backwards-compatible.
    jtag_bootstrap = 4
    booted = 5
    shell = 6
    soft_off = 7


@target_factory.reg_driver
@attr.s(eq=False)
class BootFPGASoCTFTP(Strategy):
    """Strategy to boot an FPGA SoC device using ShellDriver and TFTP.

    This strategy manages the boot process of an FPGA SoC device by utilizing
    both the ShellDriver for initial boot interactions and TFTP for kernel loading.
    It depends on a `TFTPServerResource` to provide the server IP address.
    It handles transitions through various states including powering off, booting,
    updating boot files, and entering a shell.
    """

    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "ssh": {"SSHDriver", None},
        "kuiper": {"KuiperDLDriver", None},
        # Optional JTAG bootstrap. When provided AND ps7_init_tcl /
        # uboot_elf are set, the strategy xsdb-loads U-Boot into DDR
        # before waiting for the autoboot banner. Useful when the
        # board's SD doesn't carry a working FSBL/U-Boot.
        "jtag": {"XilinxJTAGDriver", None},
        "tftp_server": "TFTPServerResource",
        "tftp_driver": "TFTPServerDriver",
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    wait_for_linux_prompt_timeout = attr.ib(default=60)
    # How long to wait for U-Boot's "Hit any key to stop autoboot"
    # banner after power-on.  Hardcoded 30 s previously — too tight
    # on slow SD or when the FPGA's FSBL takes a moment to hand off.
    wait_for_autoboot_prompt_timeout = attr.ib(default=60)
    # On a zero-byte autoboot-prompt timeout (board silent on UART),
    # power-cycle and retry this many times before raising.  Same
    # pattern the ``BootFPGASoC`` strategy uses for its
    # kernel-banner expect.
    autoboot_banner_retries = attr.ib(default=1)
    tftp_root_folder = attr.ib(default="/var/lib/tftpboot")

    # Memory addresses for boot components
    kernel_addr = attr.ib(default="0x30000000")
    dtb_addr = attr.ib(default="0x2A000000")
    # bitstream_addr = attr.ib(default="0x80000000") # Unused currently but good to have
    bootargs = attr.ib(
        default="console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlycon earlyprintk rootfstype=ext4 rootwait"
    )

    # U-Boot / platform-specific overrides.  Defaults target ZynqMP
    # (ZCU102); Zynq-7000 (ZC706) and similar platforms override these.
    uboot_prompt = attr.ib(default="ZynqMP>.*")
    kernel_image_name = attr.ib(default="Image")
    dtb_image_name = attr.ib(default="system.dtb")
    # ``booti`` is arm64 (ZynqMP); ``bootm`` is arm32 (Zynq-7000); ``bootz``
    # for raw zImage.  The command is passed as
    # ``<boot_cmd> <kernel_addr> - <dtb_addr>`` unless overridden.
    boot_cmd = attr.ib(default="booti")

    # ---------- Optional JTAG bootstrap inputs ----------------------
    # All paths are on the host that runs xsdb (the lab host bound to
    # the XilinxVivadoTool resource). Bootstrap is enabled only when
    # the ``jtag`` driver is bound AND both ``ps7_init_tcl`` and
    # ``uboot_elf`` are set; otherwise the strategy falls through to
    # the legacy "SD-bootable" path.
    ps7_init_tcl = attr.ib(default=None)
    uboot_elf = attr.ib(default=None)
    fsbl_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)
    a9_target_name = attr.ib(default="*Cortex-A9 MPCore #0")
    jtag_bootstrap_retries = attr.ib(default=2)

    def _require(self, name: str) -> str:
        """Fetch a required attr or raise StrategyError naming the field."""
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"BootFPGASoCTFTP requires '{name}' to be configured")
        return value

    def _jtag_bootstrap_enabled(self) -> bool:
        """JTAG bootstrap is opt-in: needs both the driver and the minimal
        bootstrap inputs (PS7 init TCL + U-Boot ELF). Bitstream and FSBL
        are optional refinements that ``load_zynq_uboot`` handles."""
        return bool(self.jtag) and bool(self.ps7_init_tcl) and bool(self.uboot_elf)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootFPGASoCTFTP strategy initialized")

        if self.tftp_driver:
            self.tftp_root_folder = self.tftp_driver.resource.root
            self.logger.info(f"Using managed TFTP server with root: {self.tftp_root_folder}")

        if self.kuiper:
            self.target.activate(self.kuiper)
            self.logger.info("KuiperDLDriver activated")
            self.kuiper.get_boot_files_from_release()
            self.target.deactivate(self.kuiper)

    @never_retry
    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Existing status: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            self.target.deactivate(self.shell)
            if self.tftp_driver:
                self.target.deactivate(self.tftp_driver)
            if self.jtag:
                try:
                    self.target.deactivate(self.jtag)
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
            if self.power:
                self.target.activate(self.power)
                self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.update_boot_files:
            self.transition(Status.powered_off)
            if self.tftp_driver:
                self.target.activate(self.tftp_driver)

            if not self.kuiper:
                self.logger.warning("No KuiperDLDriver attached, skipping boot file update check")
            else:
                self.logger.info(f"Preparing TFTP boot files in {self.tftp_root_folder}...")
                for boot_file in self.kuiper._boot_files:
                    self.logger.info(f"Copying {os.path.basename(boot_file)} to TFTP root...")
                    if not os.path.exists(boot_file):
                        raise StrategyError(f"Boot file {boot_file} does not exist")
                    target = os.path.join(self.tftp_root_folder, os.path.basename(boot_file))
                    shutil.copyfile(boot_file, target)
                self.logger.info("TFTP boot files prepared successfully")

        elif status == Status.booting:
            self.transition(Status.update_boot_files)
            if self.power:
                self.target.activate(self.power)
                # Explicit off → settle → on cycle clears any residual
                # board state left by the previous test / workflow run.
                # Mirror of the ``BootFPGASoC`` pre-emptive cold-cycle
                # fix — without it the first ``power.on()`` can leave
                # the board in a latched state where FSBL doesn't run
                # and the UART is completely silent until another
                # power-cycle.
                self.logger.info("Cold-cycling power to clear residual board state...")
                self.power.off()
                time.sleep(5)
                self.power.on()
            self.logger.info("Device powered on, booting...")

        elif status == Status.jtag_bootstrap:
            # Pull the board to "powered on", then (when configured)
            # xsdb-load U-Boot into DDR before the autoboot wait.
            self.transition(Status.booting)
            if not self._jtag_bootstrap_enabled():
                self.logger.info(
                    "JTAG bootstrap not configured (no `jtag` driver or "
                    "missing ps7_init_tcl/uboot_elf) — relying on the SD's "
                    "own FSBL/U-Boot"
                )
            else:
                self.target.activate(self.jtag)
                ps7 = self._require("ps7_init_tcl")
                uboot = self._require("uboot_elf")
                attempts = int(self.jtag_bootstrap_retries) + 1
                last_error: Exception | None = None
                for attempt in range(1, attempts + 1):
                    try:
                        self.logger.info(f"JTAG bootstrap attempt {attempt}/{attempts}...")
                        self.jtag.load_zynq_uboot(
                            ps7_init_tcl=ps7,
                            uboot_elf=uboot,
                            a9_target_name=self.a9_target_name,
                            bitstream_path=self.bitstream_path,
                            fsbl_elf=self.fsbl_elf,
                        )
                        break
                    except Exception as e:
                        last_error = e
                        self.logger.error(
                            f"JTAG bootstrap attempt {attempt}/{attempts} failed: {e}"
                        )
                        if attempt >= attempts:
                            raise StrategyError(f"JTAG bootstrap exhausted retries: {e}") from e
                        self.logger.info("Cold-cycling power before retry...")
                        self.target.activate(self.power)
                        self.power.off()
                        time.sleep(5)
                        self.power.on()
                else:  # pragma: no cover - loop always breaks or raises
                    raise StrategyError(f"JTAG bootstrap exhausted retries: {last_error}")
                self.logger.info("U-Boot bootstrapped via JTAG")

        elif status == Status.booted:
            self.transition(Status.jtag_bootstrap)
            self.shell.bypass_login = True
            self.target.activate(self.shell)

            # Wait for U-Boot's autoboot prompt.  Retry once on a
            # zero-byte silence — the same flake mode that
            # ``BootFPGASoC`` hits on SD-mux boards also hits TFTP
            # boards occasionally, and one more cold-cycle is enough
            # to clear it.
            attempt = 0
            max_attempts = int(self.autoboot_banner_retries) + 1
            while True:
                attempt += 1
                try:
                    self.logger.info("Waiting for U-Boot autoboot prompt...")
                    self.shell.console.expect(
                        "Hit any key to stop autoboot",
                        timeout=self.wait_for_autoboot_prompt_timeout,
                    )
                    break
                except Exception as e:
                    captured = b""
                    try:
                        captured = self.shell.console._expect.before or b""
                    except Exception:
                        pass
                    self.logger.error(
                        "Attempt %d/%d: no autoboot prompt within %ss (%d bytes captured).",
                        attempt,
                        max_attempts,
                        self.wait_for_autoboot_prompt_timeout,
                        len(captured),
                    )
                    if captured:
                        self.logger.error("Captured UART tail: %r", captured[-400:])
                    # Only retry on zero-byte silence.  If the board
                    # produced output, another power-cycle won't help.
                    if attempt >= max_attempts or len(captured) > 0 or self.power is None:
                        raise e
                    self.logger.info("Power-cycling the board and re-attempting the autoboot wait.")
                    self.target.deactivate(self.shell)
                    self.target.activate(self.power)
                    self.power.off()
                    time.sleep(5)
                    self.power.on()
                    self.logger.info("Device re-powered, booting...")
                    self.shell.bypass_login = True
                    self.target.activate(self.shell)
            self.logger.info("Stopping autoboot...")
            self.shell.console.sendline(" ")
            time.sleep(2)

            org_prompt = self.shell.prompt
            # Temporarily set prompt to U-Boot prompt match
            self.shell.prompt = self.uboot_prompt
            self.shell.console.sendline("\n")
            self.shell._check_prompt_uboot()

            # U-Boot commands configuration
            commands = [
                "setenv autoload no",
                "dhcp",
                f"setenv serverip {self.tftp_server.get_ip()}",
                f"setenv tftpdstport {self.tftp_driver.resource.port}",
                f"setenv tftpport {self.tftp_driver.resource.port}",
                "printenv tftpdstport",
                f"ping {self.tftp_server.get_ip()}",
                # Default bootargs if not set
                f"setenv bootargs {self.bootargs}",
                f"tftpboot {self.kernel_addr} {self.kernel_image_name}",
                f"tftpboot {self.dtb_addr} {self.dtb_image_name}",
            ]

            self.logger.info("Configuring U-Boot for TFTP boot...")
            for cmd in commands:
                self.logger.info(f"U-Boot: {cmd}")
                self.shell.run_uboot(f"{cmd}\n", timeout=60)  # Increased timeout for TFTP
                self.shell._check_prompt_uboot()

            # Boot the kernel; the command does not return control to U-Boot.
            self.logger.info(f"Starting kernel execution ({self.boot_cmd})...")
            self.shell.console.sendline(f"{self.boot_cmd} {self.kernel_addr} - {self.dtb_addr}")

            # Check if we reached Linux prompt
            self.logger.info(f"Waiting for Linux boot and '{self.reached_linux_marker}' prompt...")
            self.shell.prompt = org_prompt
            self.shell.console.expect(
                self.reached_linux_marker, timeout=self.wait_for_linux_prompt_timeout
            )
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.info("Device booted successfully via TFTP")

        elif status == Status.shell:
            self.transition(Status.booted)
            self.logger.info("Preparing interactive shell...")
            self.target.activate(self.shell)
            self.logger.info("Shell access ready")

        elif status == Status.soft_off:
            self.transition(Status.shell)
            try:
                self.logger.info("Triggering soft power off...")
                self.shell.run("poweroff")
                self.shell.console.expect("Power down", timeout=30)
                self.target.deactivate(self.shell)
                time.sleep(10)
            except Exception as e:
                self.logger.debug(f"Soft off failed: {e}")
                time.sleep(5)
                self.target.deactivate(self.shell)

            if self.power:
                self.target.activate(self.power)
                self.power.off()
            self.logger.info("Device powered off")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
