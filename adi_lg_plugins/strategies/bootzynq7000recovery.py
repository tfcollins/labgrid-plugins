"""Strategy to recover a Zynq-7000 board with a corrupted SD card.

Bootstraps U-Boot directly into DDR over JTAG, TFTP-loads a recovery Linux
(kernel + DTB + initramfs — rootfs in RAM), then streams a fresh SD-card
image over HTTP and ``dd``s it to ``/dev/mmcblk0``.

The caller is responsible for staging:

- ``ps7_init.tcl`` + ``u-boot.elf`` (+ optional FSBL) at host paths readable
  by xsdb.
- **FPGA bitstream** at ``bitstream_path``. Required when the recovery kernel
  has device-tree nodes for FPGA-fabric peripherals (``axi_clkgen``,
  ``axi_jesd204_*``, ``axi_adxcvr``, custom IPs). With an unprogrammed FPGA,
  the kernel's AXI probe of those addresses hangs indefinitely. The driver
  re-flashes the bitstream over JTAG before downloading U-Boot.
- Recovery ``kernel``, ``dtb``, and ``uInitrd``-style initramfs inside the
  ``TFTPServerResource.root`` directory.
- An HTTP server hosting the fresh SD image; ``python3 -m http.server`` is
  enough. The strategy fetches via the configured ``download_cmd_template``
  (default ``wget -q -O -``; override to use ``curl`` if your rootfs has it).

Building the recovery initramfs:

    The sibling :mod:`adi_lg_plugins.recovery` subpackage produces a
    suitable uImage end-to-end from a cross-compiled static busybox::

        from adi_lg_plugins.recovery import build_recovery_initramfs
        build_recovery_initramfs(
            busybox="/path/to/static/busybox",
            output="/var/lib/tftpboot/uInitrd.recovery",
        )

    Or via the CLI::

        adi-lg build-recovery-initramfs \\
            --busybox /path/to/busybox \\
            --out /var/lib/tftpboot/uInitrd.recovery

    The builder bundles the ``/init`` getty-emulating script, the
    ``udhcpc`` hook, busybox applet symlinks (sh/dd/wget/mktemp/rx/...),
    and the required device nodes (``/dev/console`` etc.).

See ``examples/zynq7000_recovery/`` for the per-board YAML and a
customization recipe.
"""

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for the SD recovery flow."""

    unknown = 0
    powered_off = 1
    powered_on = 2
    jtag_bootstrap = 3
    uboot_prompt = 4
    tftp_recovery_kernel = 5
    linux_recovery = 6
    sd_flash_done = 7
    soft_off = 8


@target_factory.reg_driver
@attr.s(eq=False)
class BootZynq7000JTAGRecovery(Strategy):
    """Recover a Zynq-7000 board with a corrupted SD card.

    Workflow:
        1. Cold-cycle power.
        2. JTAG-bootstrap U-Boot into DDR via xsdb (``ps7_init.tcl`` +
           optional FPGA ``bitstream`` + ``u-boot.elf``).
        3. Interrupt U-Boot autoboot on serial.
        4. TFTP-load recovery kernel/DTB/initramfs; ``bootm`` into RAM-rooted
           Linux.
        5. From Linux userspace, ``wget <sd_image_url> | dd of=/dev/mmcblk0``.

    The strategy stops at ``sd_flash_done``; verifying the freshly-flashed SD
    boots cleanly is the caller's job (chain a separate ``BootFPGASoCTFTP`` or
    ``BootFPGASoC`` transition afterward).

    Generic across Zynq-7000 boards; board-specific values (memory addresses,
    DTB filename, ``ps7_init.tcl`` path) are all attributes.
    """

    bindings = {
        "power": "PowerProtocol",
        "jtag": "XilinxJTAGDriver",
        "shell": "ADIShellDriver",
        "tftp_server": "TFTPServerResource",
        "tftp_driver": "TFTPServerDriver",
        "ssh": {"SSHDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    # JTAG bootstrap inputs (paths on the host that runs xsdb)
    ps7_init_tcl = attr.ib(default=None)
    uboot_elf = attr.ib(default=None)
    fsbl_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)
    a9_target_name = attr.ib(default="*Cortex-A9 MPCore #0")

    # Recovery image inputs (filenames inside tftp_root_folder)
    recovery_kernel = attr.ib(default=None)
    recovery_dtb = attr.ib(default=None)
    recovery_initramfs = attr.ib(default=None)
    recovery_login_marker = attr.ib(default="recovery login:")

    # SD flash inputs
    sd_image_url = attr.ib(default=None)
    sd_device = attr.ib(default="/dev/mmcblk0")
    download_cmd_template = attr.ib(default='wget -q -O - "{url}"')

    # U-Boot env (Zynq-7000 = arm32: bootm + zImage + uInitrd)
    uboot_prompt = attr.ib(default="zynq-uboot>|U-Boot>|=>")
    kernel_addr = attr.ib(default="0x2080000")
    dtb_addr = attr.ib(default="0x2000000")
    initramfs_addr = attr.ib(default="0x4000000")
    # Default uses ``rdinit=/init`` (the cpio's own ``/init`` script) rather
    # than ``rdinit=/sbin/init``: with an initramfs rootfs the kernel uses
    # ``rootfs`` directly and ``/sbin/init`` symlinks are inconsistent
    # across busybox configurations. No ``root=`` because the kernel uses
    # the unpacked initramfs as rootfs.
    bootargs = attr.ib(default="console=ttyPS0,115200 earlyprintk loglevel=8 rdinit=/init")

    # Robustness
    jtag_bootstrap_retries = attr.ib(default=2)
    wait_for_uboot_prompt_timeout = attr.ib(default=60)
    wait_for_recovery_linux_timeout = attr.ib(default=180)
    wait_for_sd_flash_timeout = attr.ib(default=1800)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootZynq7000JTAGRecovery strategy initialized")

    def _require(self, name: str) -> str:
        """Fetch a required attr or raise StrategyError naming the field."""
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"BootZynq7000JTAGRecovery requires '{name}' to be configured")
        return value

    def _cold_cycle(self) -> None:
        """Off → settle → on. Clears residual board state."""
        self.target.activate(self.power)
        self.power.off()
        time.sleep(5)
        self.power.on()

    def _build_sd_flash_cmd(self) -> str:
        """Compose the streaming download | dd one-liner for the recovery shell."""
        sd_image_url = self._require("sd_image_url")
        download_cmd = self.download_cmd_template.format(url=sd_image_url)
        return (
            f'test -b "{self.sd_device}" && '
            f'{download_cmd} | dd of="{self.sd_device}" bs=4M conv=fsync && '
            f"sync && echo SD_FLASH_OK"
        )

    @never_retry
    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Current: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            self.target.deactivate(self.shell)
            if self.tftp_driver:
                self.target.deactivate(self.tftp_driver)
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            self.logger.info("Cold-cycling power...")
            self._cold_cycle()
            self.logger.info("Device powered on")

        elif status == Status.jtag_bootstrap:
            self.transition(Status.powered_on)
            ps7_init_tcl = self._require("ps7_init_tcl")
            uboot_elf = self._require("uboot_elf")

            self.target.activate(self.jtag)
            attempts = int(self.jtag_bootstrap_retries) + 1
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    self.logger.info(f"JTAG bootstrap attempt {attempt}/{attempts}...")
                    self.jtag.load_zynq_uboot(
                        ps7_init_tcl=ps7_init_tcl,
                        uboot_elf=uboot_elf,
                        a9_target_name=self.a9_target_name,
                        bitstream_path=self.bitstream_path,
                        fsbl_elf=self.fsbl_elf,
                    )
                    break
                except Exception as e:
                    last_error = e
                    self.logger.error(f"JTAG bootstrap attempt {attempt}/{attempts} failed: {e}")
                    if attempt >= attempts:
                        raise StrategyError(f"JTAG bootstrap exhausted retries: {e}") from e
                    self.logger.info("Cold-cycling power before retry...")
                    self._cold_cycle()
            else:  # pragma: no cover - loop always breaks or raises
                raise StrategyError(f"JTAG bootstrap exhausted retries: {last_error}")
            self.logger.info("U-Boot bootstrapped via JTAG")

        elif status == Status.uboot_prompt:
            self.transition(Status.jtag_bootstrap)
            self.target.activate(self.tftp_driver)
            self.shell.bypass_login = True
            self.target.activate(self.shell)

            attempts = 2
            for attempt in range(1, attempts + 1):
                try:
                    self.logger.info("Waiting for U-Boot autoboot prompt...")
                    self.shell.console.expect(
                        "Hit any key to stop autoboot",
                        timeout=self.wait_for_uboot_prompt_timeout,
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
                        attempts,
                        self.wait_for_uboot_prompt_timeout,
                        len(captured),
                    )
                    if captured:
                        self.logger.error("Captured UART tail: %r", captured[-400:])
                    if attempt >= attempts or len(captured) > 0:
                        raise e
                    self.logger.info("Re-bootstrapping U-Boot via JTAG before retry...")
                    self.target.deactivate(self.shell)
                    self._cold_cycle()
                    self.jtag.load_zynq_uboot(
                        ps7_init_tcl=self.ps7_init_tcl,
                        uboot_elf=self.uboot_elf,
                        a9_target_name=self.a9_target_name,
                        bitstream_path=self.bitstream_path,
                        fsbl_elf=self.fsbl_elf,
                    )
                    self.shell.bypass_login = True
                    self.target.activate(self.shell)

            self.logger.info("Stopping autoboot...")
            self.shell.console.sendline(" ")
            time.sleep(2)
            self._original_prompt = self.shell.prompt
            self.shell.prompt = self.uboot_prompt
            self.shell.console.sendline("\n")
            self.shell._check_prompt_uboot()
            self.logger.info("U-Boot prompt reached")

        elif status == Status.tftp_recovery_kernel:
            self.transition(Status.uboot_prompt)
            kernel = self._require("recovery_kernel")
            dtb = self._require("recovery_dtb")
            initramfs = self._require("recovery_initramfs")

            commands = [
                "setenv autoload no",
                "dhcp",
                f"setenv serverip {self.tftp_server.get_ip()}",
                f"setenv tftpdstport {self.tftp_driver.resource.port}",
                f"setenv tftpport {self.tftp_driver.resource.port}",
                f"setenv bootargs {self.bootargs}",
                f"tftpboot {self.kernel_addr} {kernel}",
                f"tftpboot {self.dtb_addr} {dtb}",
                f"tftpboot {self.initramfs_addr} {initramfs}",
            ]
            self.logger.info("Configuring U-Boot for recovery TFTP boot...")
            for cmd in commands:
                self.logger.info(f"U-Boot: {cmd}")
                self.shell.run_uboot(f"{cmd}\n", timeout=60)
                self.shell._check_prompt_uboot()

            bootm = f"bootm {self.kernel_addr} {self.initramfs_addr} {self.dtb_addr}"
            self.logger.info(f"Launching recovery kernel: {bootm}")
            self.shell.console.sendline(bootm)

        elif status == Status.linux_recovery:
            self.transition(Status.tftp_recovery_kernel)
            self.logger.info(f"Waiting for recovery login marker '{self.recovery_login_marker}'...")
            self.shell.console.expect(
                self.recovery_login_marker,
                timeout=self.wait_for_recovery_linux_timeout,
            )
            # Restore original prompt and re-activate shell with login.
            if hasattr(self, "_original_prompt"):
                self.shell.prompt = self._original_prompt
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.target.activate(self.shell)
            self.logger.info("Recovery Linux shell ready")

        elif status == Status.sd_flash_done:
            self.transition(Status.linux_recovery)
            # Inline ``shell.run`` rather than ``shell.run_script`` — the latter
            # pushes the script via XMODEM, which expects a stable post-transfer
            # prompt return that busybox ``rx`` over a raw initramfs console
            # didn't deliver reliably in testing.
            cmd = self._build_sd_flash_cmd()
            self.logger.info(
                f"Streaming SD image to {self.sd_device} (timeout {self.wait_for_sd_flash_timeout}s)..."
            )
            stdout, stderr, returncode = self.shell.run(cmd, timeout=self.wait_for_sd_flash_timeout)
            stdout_str = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
            stderr_str = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
            if returncode != 0 or "SD_FLASH_OK" not in stdout_str:
                raise StrategyError(
                    f"SD flash failed (rc={returncode}): {stderr_str or stdout_str}"
                )
            self.logger.info("SD card reflashed successfully")

        elif status == Status.soft_off:
            self.transition(Status.sd_flash_done)
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
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
