"""Strategy to re-image the Versal SD card on a VPK180 via QSPI rescue + TFTP + SC."""

import enum
import os
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError

from ._compat import never_retry


class Status(enum.Enum):
    """ReflashVPK180SD state machine states."""

    unknown = 0
    powered_off = 1
    image_staged = 2
    sc_in_qspi = 3
    recovery_booted = 4
    sd_written = 5
    sc_in_sd = 6
    done = 7


class BoardLeftInQSPIMode(StrategyError):
    """Raised when the SD reflash succeeded but the SC failed to restore SD bootmode.

    The board will reboot into QSPI recovery on next power-on. To recover:
      - Manually open the SC console and run:
            sc_app -c setbootmode -t SD
            sc_app -c reset
      - Or re-run the strategy targeting Status.sc_in_sd.
    """


@target_factory.reg_driver
@attr.s(eq=False)
class ReflashVPK180SD(Strategy):
    """Re-image the VPK180's Versal SD card from a Kuiper release via QSPI rescue.

    Precondition (one-time, per board): QSPI must already contain a bootable
    image (U-Boot + minimal Linux with BusyBox tftp + dd). On VPK180 this can
    be programmed using xsdb on the SC; see the project docs for the
    procedure. AMD's prebuilt ``2022.2_vpk180_release.tar.xz`` BSP or a
    Kuiper release's BOOT.BIN both work as the rescue image.

    Flow:

    1. ``image_staged`` — download the Kuiper SD image (if not cached) and
       symlink/copy it under the local TFTP daemon's root.
    2. ``sc_in_qspi`` — SC switches Versal bootmode to QSPI32 and resets it.
    3. ``recovery_booted`` — Versal boots from QSPI; strategy logs in via
       ``target_shell`` (ADIShellDriver does the login flow with normal
       prompt/username/password configured in YAML).
    4. ``sd_written`` — recovery Linux runs the configured ``dd_command_template``
       which TFTPs the image and pipes into ``dd`` of the target SD device.
    5. ``sc_in_sd`` — SC switches bootmode back to SD and resets the Versal.
    6. ``done`` — board powered off (configurable). The SD now has a fresh
       Kuiper image, ready for ``BootVPK180`` to bring it up normally.

    Bindings:
        power: PowerProtocol — board power (e.g., HomeAssistantPowerDriver)
        sc_shell: ADIShellDriver — system controller PetaLinux UART (ttyUSB3)
        target_shell: ADIShellDriver — Versal recovery Linux UART (ttyUSB1)
        kuiper: KuiperDLDriver — source of the full SD image
        tftp: TFTPServerDriver — serves the image to the recovery Linux

    The two ADIShellDriver instances are name-disambiguated in YAML; mirrors
    the BootVPK180 pattern.

    Hang recovery: each SC and recovery-banner phase cold-cycles the board on
    timeout, bounded by per-site retry counters defaulting to 3. The dd phase
    is *not* cold-cycled (recovery Linux is still up); ``dd_retries=1`` retries
    the pipe once for transient TFTP packet loss. dd I/O errors are fatal —
    cold-cycling won't help an oversized or bad SD.

    The strategy never sends data on the Versal UART during the kernel-banner
    watch (``bypass_login=True``) so it cannot accidentally interrupt U-Boot
    autoboot.

    Attributes:
        sc_to_qspi_commands: List of SC shell commands to switch Versal to
            QSPI32 boot mode and reset. Default targets sc_app.
        sc_to_sd_commands: List of SC shell commands to restore SD boot mode
            and reset. Default targets sc_app.
        recovery_kernel_banner_pattern: String/regex on the Versal UART that
            confirms the QSPI rescue kernel started. Default ``"Starting kernel"``.
        tftp_image_filename: Filename inside the TFTP server root that the
            recovery Linux will request. Default ``"kuiper.img"``.
        target_sd_device: SD block device name on the recovery Linux.
            Default ``"/dev/mmcblk0"``.
        dd_block_size: ``bs=`` value for dd. Default ``"4M"``.
        dd_command_template: Shell command template, interpolated with
            ``server_ip``, ``server_port``, ``filename``, ``dev``, ``bs``.
            Default uses BusyBox ``tftp -g -l - | dd``; override for systems
            without ``-l -`` support.
        dd_timeout: Per-attempt timeout in seconds. Default 1800 (30 min).
        dd_retries: In-place dd retry count. Default 1. No cold-cycle between
            retries; the recovery shell stays up.
        verify_after_write: When True, after dd succeeds the strategy runs
            a verification command that re-fetches the image and compares
            sha256.
        verify_command_template: Shell command for verification.
        stage_method: How to place the cached image into the TFTP root.
            One of ``"symlink"``, ``"hardlink"``, ``"copy"``. Default
            ``"symlink"`` — fastest, no extra disk; falls back automatically
            on cross-filesystem failure with a clear error.
        sc_login_retries / sc_command_retries / recovery_banner_retries:
            Cold-cycle retry counters per phase. Default 3 each.
        wait_for_sc_command_timeout: Per-SC-command timeout in seconds.
            Default 30.
        wait_for_recovery_banner_timeout: Timeout in seconds to wait for
            ``recovery_kernel_banner_pattern`` after switching to QSPI.
            Default 120.
        wait_for_recovery_login_timeout: Timeout for the recovery Linux
            login flow. Default 60. (Configures target_shell in YAML directly
            for fine control.)
        power_off_when_done: If True, power off the board after restoring SD
            bootmode. Default True.
        restore_sd_bootmode: If False, skip the ``sc_in_sd`` phase (board
            stays in QSPI for further work). Default True.
        debug_write_uart_log: When True, every retry writes a per-phase
            UART log file for post-mortem.
    """

    bindings = {
        "power": "PowerProtocol",
        "sc_shell": "ADIShellDriver",
        "target_shell": "ADIShellDriver",
        "kuiper": "KuiperDLDriver",
        "tftp": "TFTPServerDriver",
    }

    status = attr.ib(default=Status.unknown)

    sc_to_qspi_commands = attr.ib(
        factory=lambda: ["sc_app -c setbootmode -t QSPI32", "sc_app -c reset"]
    )
    sc_to_sd_commands = attr.ib(factory=lambda: ["sc_app -c setbootmode -t SD", "sc_app -c reset"])

    recovery_kernel_banner_pattern = attr.ib(default="Starting kernel")

    tftp_image_filename = attr.ib(default="kuiper.img")
    target_sd_device = attr.ib(default="/dev/mmcblk0")
    dd_block_size = attr.ib(default="4M")
    dd_command_template = attr.ib(
        default=(
            "set -o pipefail; "
            "tftp -g -r {filename} -l - {server_ip} {server_port} | "
            "dd of={dev} bs={bs} status=progress conv=fsync"
        )
    )
    dd_timeout = attr.ib(default=1800)
    dd_retries = attr.ib(default=1)
    verify_after_write = attr.ib(default=False)
    verify_command_template = attr.ib(
        default=(
            "tftp -g -r {filename} -l - {server_ip} {server_port} | "
            "head -c $(blockdev --getsize64 {dev}) | sha256sum"
        )
    )

    stage_method = attr.ib(default="symlink")

    sc_login_retries = attr.ib(default=3)
    sc_command_retries = attr.ib(default=3)
    recovery_banner_retries = attr.ib(default=3)

    wait_for_sc_command_timeout = attr.ib(default=30)
    wait_for_recovery_banner_timeout = attr.ib(default=120)
    wait_for_recovery_login_timeout = attr.ib(default=60)

    power_off_when_done = attr.ib(default=True)
    restore_sd_bootmode = attr.ib(default=True)

    boot_log = attr.ib(default="", init=False)
    debug_write_uart_log = attr.ib(default=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("ReflashVPK180SD strategy initialized")
        # Note: do NOT pre-warm Kuiper here. The SD image is multi-GB; only
        # download when the user actually transitions to image_staged.

    # ---- helpers (mirrored from BootVPK180) ---------------------------------

    def _cold_cycle(self):
        """Hard power off → settle → on, deactivating any active shells first."""
        for shell in (self.sc_shell, self.target_shell):
            try:
                self.target.deactivate(shell)
            except Exception:
                pass
        self.target.activate(self.power)
        self.power.off()
        time.sleep(5)
        self.power.on()

    def _dump_uart(self, console, phase, attempt):
        if not self.debug_write_uart_log:
            return
        try:
            captured = console._expect.before or b""
        except Exception:
            captured = b""
        path = f"uart_log_{phase}_attempt{attempt}_{int(time.time())}.txt"
        try:
            with open(path, "wb") as f:
                f.write(captured)
            self.logger.info("Wrote UART log to %s", path)
        except Exception as e:
            self.logger.warning("Failed to write UART log %s: %s", path, e)

    def _wait_for_sc_alive(self):
        """Activate the SC shell, retrying with cold-cycles on login timeout."""
        attempt = 0
        max_attempts = int(self.sc_login_retries) + 1
        while True:
            attempt += 1
            try:
                self.sc_shell.bypass_login = False
                self.target.activate(self.sc_shell)
                self.logger.info("SC shell active (attempt %d)", attempt)
                return
            except Exception as e:
                self.logger.error(
                    "Attempt %d/%d: SC shell login failed: %s",
                    attempt,
                    max_attempts,
                    e,
                )
                self._dump_uart(self.sc_shell.console, "sc_login", attempt)
                if attempt >= max_attempts:
                    raise
                self.logger.info("Cold-cycling and retrying SC login.")
                self._cold_cycle()

    def _run_sc_commands(self, commands):
        """Run a list of shell commands on SC. Cold-cycle and restart on failure."""
        if not commands:
            self.logger.info("No SC commands configured for this phase.")
            return

        attempt = 0
        max_attempts = int(self.sc_command_retries) + 1
        while True:
            attempt += 1
            try:
                for cmd in commands:
                    self.logger.info("SC command (attempt %d): %s", attempt, cmd)
                    self.sc_shell.run_check(cmd, timeout=self.wait_for_sc_command_timeout)
                self.logger.info("SC command sequence complete")
                return
            except Exception as e:
                self.logger.error(
                    "Attempt %d/%d: SC command sequence failed: %s",
                    attempt,
                    max_attempts,
                    e,
                )
                self._dump_uart(self.sc_shell.console, "sc_command", attempt)
                if attempt >= max_attempts:
                    raise
                self.logger.info("Cold-cycling and restarting SC phase.")
                self._cold_cycle()
                self._wait_for_sc_alive()

    # ---- phase methods ------------------------------------------------------

    def _stage_one_file(self, src, dst):
        """Place src into dst per stage_method. Falls back with clear error."""
        if os.path.exists(dst) or os.path.islink(dst):
            os.remove(dst)
        if self.stage_method == "symlink":
            try:
                os.symlink(src, dst)
                return
            except OSError as e:
                raise StrategyError(
                    f"stage_method='symlink' failed ({e}); set stage_method='copy' "
                    f"if Kuiper cache and TFTP root are on different filesystems."
                ) from e
        if self.stage_method == "hardlink":
            try:
                os.link(src, dst)
                return
            except OSError as e:
                raise StrategyError(
                    f"stage_method='hardlink' failed ({e}); use 'copy' across filesystems."
                ) from e
        if self.stage_method == "copy":
            import shutil

            shutil.copyfile(src, dst)
            return
        raise StrategyError(
            f"unknown stage_method={self.stage_method!r}; use 'symlink', 'hardlink', or 'copy'."
        )

    def _stage_image_to_tftp(self):
        """Download the Kuiper image (cached) and place it under the TFTP root."""
        self.logger.info("Staging Kuiper image to TFTP root...")
        self.target.activate(self.kuiper)
        try:
            img_path = self.kuiper.get_full_image_path()
        finally:
            try:
                self.target.deactivate(self.kuiper)
            except Exception:
                pass

        self.target.activate(self.tftp)
        tftp_root = self.tftp.resource.root
        if not os.path.exists(tftp_root):
            os.makedirs(tftp_root)
        dst = os.path.join(tftp_root, self.tftp_image_filename)
        self.logger.info("Staging %s → %s (%s)", img_path, dst, self.stage_method)
        self._stage_one_file(img_path, dst)

        size = os.path.getsize(dst)
        if size > 32 * 1024 * 1024:
            self.logger.warning(
                "Staged image is %.1f MB; the bundled SimpleTFTPServer wraps RFC 1350 "
                "block numbers at 32 MB. Most modern clients tolerate the wrap, but "
                "if dd fails on multiples of 32 MB, RFC 2348 blksize support is needed.",
                size / 1024 / 1024,
            )
        self.logger.info(
            "TFTP server: %s:%s, root=%s, file=%s",
            self.tftp.resource.get_ip(),
            self.tftp.resource.port,
            tftp_root,
            self.tftp_image_filename,
        )

    def _wait_for_recovery_kernel(self):
        """Watch the Versal UART for the rescue kernel banner.

        On timeout, cold-cycle, redo the SC-into-QSPI phase, and re-watch.
        Retries bounded by recovery_banner_retries.
        """
        self.target_shell.bypass_login = True
        self.target.activate(self.target_shell)

        attempt = 0
        max_attempts = int(self.recovery_banner_retries) + 1
        while True:
            attempt += 1
            try:
                _, before, _, _ = self.target_shell.console.expect(
                    self.recovery_kernel_banner_pattern,
                    timeout=self.wait_for_recovery_banner_timeout,
                )
                if before:
                    self.boot_log += before.decode("utf-8", errors="replace")
                return
            except Exception as e:
                captured = b""
                try:
                    captured = self.target_shell.console._expect.before or b""
                except Exception:
                    pass
                self._dump_uart(self.target_shell.console, "recovery_banner", attempt)
                self.logger.error(
                    "Attempt %d/%d: no recovery kernel banner within %ss (%d bytes captured).",
                    attempt,
                    max_attempts,
                    self.wait_for_recovery_banner_timeout,
                    len(captured),
                )
                if captured:
                    self.logger.error("Captured Versal UART tail: %r", captured[-400:])
                if attempt >= max_attempts:
                    raise e
                self.logger.info("Cold-cycling, redoing SC into QSPI, re-watching Versal UART.")
                self.target.deactivate(self.target_shell)
                self._cold_cycle()
                self._wait_for_sc_alive()
                self._run_sc_commands(self.sc_to_qspi_commands)
                self.target.deactivate(self.sc_shell)
                self.target_shell.bypass_login = True
                self.target.activate(self.target_shell)

    def _login_to_recovery(self):
        """After the kernel banner, drive ADIShellDriver's normal login flow.

        Toggles bypass_login back to False and re-activates target_shell so
        ADIShellDriver runs its ``_await_login`` against the recovery Linux's
        ``login:`` prompt (configured in YAML).
        """
        self.target.deactivate(self.target_shell)
        self.target_shell.bypass_login = False
        self.target.activate(self.target_shell)
        self.logger.info("Recovery Linux logged in")

    def _write_sd_from_recovery(self):
        """Issue the dd command on the recovery shell and verify if requested."""
        server_ip = self.tftp.resource.get_ip()
        server_port = self.tftp.resource.port
        cmd = self.dd_command_template.format(
            filename=self.tftp_image_filename,
            server_ip=server_ip,
            server_port=server_port,
            dev=self.target_sd_device,
            bs=self.dd_block_size,
        )
        attempt = 0
        max_attempts = int(self.dd_retries) + 1
        while True:
            attempt += 1
            self.logger.info("dd attempt %d/%d: %s", attempt, max_attempts, cmd)
            try:
                self.target_shell.run_check(cmd, timeout=self.dd_timeout)
                self.logger.info("dd completed successfully")
                if self.verify_after_write:
                    self._verify_sd(server_ip, server_port)
                return
            except Exception as e:
                self.logger.error("Attempt %d/%d: dd failed: %s", attempt, max_attempts, e)
                if attempt >= max_attempts:
                    raise
                # No cold-cycle — recovery Linux is still up; just retry.

    def _verify_sd(self, server_ip, server_port):
        cmd = self.verify_command_template.format(
            filename=self.tftp_image_filename,
            server_ip=server_ip,
            server_port=server_port,
            dev=self.target_sd_device,
            bs=self.dd_block_size,
        )
        self.logger.info("Verifying SD contents: %s", cmd)
        self.target_shell.run_check(cmd, timeout=self.dd_timeout)

    # ---- state machine ------------------------------------------------------

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Drive the state machine toward ``status``.

        States are walked in order; requesting ``done`` will transition through
        every prior state needed.
        """
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info("Transitioning to %s (existing status: %s)", status, self.status)

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            for shell in (self.sc_shell, self.target_shell):
                try:
                    self.target.deactivate(shell)
                except Exception:
                    pass
            try:
                self.target.deactivate(self.tftp)
            except Exception:
                pass
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Board powered off")

        elif status == Status.image_staged:
            self.transition(Status.powered_off)
            self._stage_image_to_tftp()

        elif status == Status.sc_in_qspi:
            self.transition(Status.image_staged)
            self.target.activate(self.power)
            self.logger.info("Cold-cycling power before SC orchestration...")
            self.power.off()
            time.sleep(5)
            self.power.on()
            self._wait_for_sc_alive()
            self._run_sc_commands(self.sc_to_qspi_commands)
            self.target.deactivate(self.sc_shell)

        elif status == Status.recovery_booted:
            self.transition(Status.sc_in_qspi)
            self.boot_log = ""
            self._wait_for_recovery_kernel()
            self._login_to_recovery()

        elif status == Status.sd_written:
            self.transition(Status.recovery_booted)
            self._write_sd_from_recovery()

        elif status == Status.sc_in_sd:
            self.transition(Status.sd_written)
            if not self.restore_sd_bootmode:
                self.logger.info("restore_sd_bootmode=False; skipping SC bootmode restore")
            else:
                try:
                    self.target.deactivate(self.target_shell)
                except Exception:
                    pass
                try:
                    self._wait_for_sc_alive()
                    self._run_sc_commands(self.sc_to_sd_commands)
                except Exception as e:
                    raise BoardLeftInQSPIMode(
                        "SD reflash succeeded but SC failed to restore SD bootmode. "
                        "Manually run on SC: 'sc_app -c setbootmode -t SD; sc_app -c reset', "
                        "or re-run this strategy targeting Status.sc_in_sd."
                    ) from e
                finally:
                    try:
                        self.target.deactivate(self.sc_shell)
                    except Exception:
                        pass

        elif status == Status.done:
            self.transition(Status.sc_in_sd)
            if self.power_off_when_done:
                self.target.activate(self.power)
                self.power.off()
                self.logger.info("Board powered off; reflash complete")
            try:
                self.target.deactivate(self.tftp)
            except Exception:
                pass

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
