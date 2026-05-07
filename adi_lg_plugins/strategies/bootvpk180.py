"""Strategy to boot AMD Versal Premium VPK180 boards via the Zynq system controller."""

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for VPK180 boot via SC + Versal.

    Attributes:
        unknown: Initial state before any operations.
        powered_off: Board is powered off.
        sd_mux_to_host: SD card muxed to host (only entered when sdmux is bound).
        update_boot_files: Boot files staged via SD-mux or SSH.
        sd_mux_to_dut: SD card muxed back to DUT (only entered when sdmux is bound).
        booting: Board powered on, awaiting SC then Versal boot.
        booted: Versal has reached the configured Linux marker.
        shell: Interactive shell session available on the Versal.
        soft_off: Device being shut down gracefully.
    """

    unknown = 0
    powered_off = 1
    sd_mux_to_host = 2
    update_boot_files = 3
    sd_mux_to_dut = 4
    booting = 5
    booted = 6
    shell = 7
    soft_off = 8


@target_factory.reg_driver
@attr.s(eq=False)
class BootVPK180(Strategy):
    """Boot strategy for AMD Versal Premium VPK180 with a Zynq system controller.

    The VPK180 has two Linux systems involved in bring-up: a Zynq-based System
    Controller (SC) running PetaLinux on its own eMMC, and the Versal target
    that boots from QSPI/SD. The SC's UART (typically ttyUSB3) is used to
    orchestrate the board (login, run board-management commands, release the
    Versal). The Versal's UART (typically ttyUSB1) hosts the actual Linux that
    user tests interact with.

    Both consoles are wired as ``ADIShellDriver`` instances on the target,
    differentiated by binding name. The SC shell logs in automatically on
    activation; the target shell is read in ``bypass_login`` mode while
    watching for the Versal kernel banner, then re-activated for an
    interactive prompt at the ``shell`` state.

    Image / boot-file update has three modes, selected by which optional
    bindings are present:

    * **SD-mux** (``sdmux`` + ``mass_storage`` bindings, optionally
      ``image_writer``): identical flow to ``BootFPGASoC`` — mux SD to host,
      write boot files (or full image), mux back to DUT.
    * **SSH** (``ssh`` binding only): copy boot files into the running
      Versal Linux's boot partition over SCP, ``sync``, then issue a reboot.
      Requires the Versal to currently be running a usable Linux. The next
      cold-cycle in ``Status.booting`` makes the reboot belt-and-suspenders.
    * **None**: ``update_boot_files=False`` skips file staging and boots
      whatever is already on QSPI/SD.

    SD-mux is preferred when both are available — it works from cold,
    SSH does not.

    Hang recovery: the SC and Versal can both fail to come up cleanly. The
    strategy cold-cycles power on each failure site, bounded by per-site
    retry counters that default to 3 so transient issues self-recover:

    * SC login (``sc_login_retries``): pexpect timeout while activating the
      SC shell — typically zero-byte silence on the SC UART or stuck mid-boot.
    * SC command (``sc_command_retries``): a configured ``sc_commands`` entry
      didn't return within ``wait_for_sc_command_timeout``. Recovery restarts
      the entire SC phase from a cold-cycled board.
    * Versal kernel banner (``kernel_banner_retries``): the target UART
      didn't produce ``kernel_banner_pattern`` within
      ``wait_for_kernel_banner_timeout``. The expectation is that an
      uninterrupted Versal SD boot reaches Linux every time; *any* timeout —
      whether silent or stuck-at-U-Boot-prompt — gets a cold-cycle retry,
      because power-cycling clears most transient board states. Only after
      retries are exhausted do we surface the failure.

    The strategy never sends data on the Versal UART during boot watch
    (``bypass_login=True``), so it cannot accidentally interrupt U-Boot
    autoboot.

    Attributes:
        reached_linux_marker: String/regex on the Versal UART that confirms
            user-space Linux is up. Default ``"analog"`` (matches Kuiper).
        sc_commands: Ordered list of shell commands to run on the SC after
            login. Each is executed via ``sc_shell.run_check`` with
            ``wait_for_sc_command_timeout``. The default is empty: the
            strategy will simply confirm the SC is alive and then watch the
            Versal UART for boot. AMD does not document a stable CLI for
            "reset Versal target" — the BEAM web UI does this via
            board-specific GPIO toggles. Configure the right command(s) for
            your SC firmware in YAML.
        wait_for_sc_command_timeout: Per-command timeout for ``sc_commands``.
        wait_for_kernel_banner_timeout: How long to wait for the first
            ``Linux`` banner on the Versal UART after SC orchestration.
        wait_for_linux_prompt_timeout: How long to wait for
            ``reached_linux_marker`` after the kernel banner.
        sc_login_retries: Cold-cycle retries on SC login timeout. Default 1.
        sc_command_retries: Cold-cycle retries when an SC command times out.
            Default 1. A retry restarts the whole SC phase from cold.
        kernel_banner_retries: Cold-cycle retries on zero-byte Versal silence.
            Default 1.
        update_image: Write a full image via ``image_writer`` (requires sdmux
            + image_writer + kuiper).
        update_boot_files: Stage boot files via SD-mux or SSH. Requires
            ``kuiper`` plus one of (sdmux + mass_storage) or ``ssh``.
        boot_partition_path: Target directory for the SSH file-update path.
            Default ``/boot``.
        ssh_reboot_command: Reboot command issued after SSH copy. Default
            ``sudo reboot``. Fire-and-forget — we always cold-cycle next.
        debug_write_boot_log: When True, every retry writes a per-phase UART
            log file for post-mortem.
    """

    bindings = {
        # required
        "power": "PowerProtocol",
        "sc_shell": "ADIShellDriver",
        "target_shell": "ADIShellDriver",
        # optional — file-update paths
        "sdmux": {"USBSDMuxDriver", None},
        "mass_storage": {"MassStorageDriver", None},
        "image_writer": {"USBStorageDriver", None},
        "kuiper": {"KuiperDLDriver", None},
        "ssh": {"SSHDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    # Pattern signaling the Versal kernel actually started. The literal "Linux"
    # used by BootFPGASoC is too loose here — it matches inside U-Boot error
    # strings like "Bad Linux ARM64 Image magic!". "Starting kernel" is U-Boot's
    # last message before jumping to the kernel and is reliably absent from
    # error messages; override to "Linux version " or similar if your boot
    # output uses different framing.
    kernel_banner_pattern = attr.ib(default="Starting kernel")

    sc_commands = attr.ib(factory=list)

    wait_for_sc_command_timeout = attr.ib(default=30)
    wait_for_kernel_banner_timeout = attr.ib(default=120)
    wait_for_linux_prompt_timeout = attr.ib(default=60)

    # Cold-cycle retry counts. Every failure-mode below cold-cycles the whole
    # board and reattempts; SC hangs and Versal-not-reaching-Linux are both
    # expected to clear with a fresh power-on under normal operation. Default
    # 3 so transient board issues self-recover.
    sc_login_retries = attr.ib(default=3)
    sc_command_retries = attr.ib(default=3)
    kernel_banner_retries = attr.ib(default=3)

    update_image = attr.ib(default=False)
    update_boot_files = attr.ib(default=False)
    boot_partition_path = attr.ib(default="/boot")
    ssh_reboot_command = attr.ib(default="sudo reboot")

    # When True, transition(booting) probes the SC with a short timeout first
    # and skips the explicit cold-cycle if the SC is already responsive. The
    # Versal target is then restarted by the sc_app -c reset command in
    # sc_commands rather than by a board power-cycle. Reduces test time and
    # avoids SC-wedge modes triggered by repeated power cycling. Skipped
    # automatically when update_image or update_boot_files is True (those
    # paths must go through powered_off → file staging → cold-cycle).
    warm_boot_if_sc_alive = attr.ib(default=True)
    warm_probe_timeout = attr.ib(default=3)

    boot_log = attr.ib(default="", init=False)
    debug_write_boot_log = attr.ib(default=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootVPK180 strategy initialized")
        kuiper = getattr(self, "kuiper", None)
        if kuiper:
            self.logger.info("Preloading Kuiper boot files")
            self.target.activate(kuiper)
            kuiper.get_boot_files_from_release()
            self.target.deactivate(kuiper)

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

    def _sc_appears_alive(self):
        """Non-destructive check: is the SC at a Linux prompt right now?

        Activates sc_shell with bypass_login=True (no-op on_activate), pokes
        the console with a newline, looks for the configured prompt within
        ``warm_probe_timeout`` seconds. Always deactivates and restores
        bypass_login afterward. Returns False on any error.
        """
        prior_bypass = getattr(self.sc_shell, "bypass_login", False)
        activated = False
        try:
            self.sc_shell.bypass_login = True
            self.target.activate(self.sc_shell)
            activated = True
            self.sc_shell.console.sendline("")
            try:
                self.sc_shell.console.expect(self.sc_shell.prompt, timeout=self.warm_probe_timeout)
                return True
            except Exception:
                return False
        except Exception as e:
            self.logger.debug("Warm SC probe failed during activation: %s", e)
            return False
        finally:
            if activated:
                try:
                    self.target.deactivate(self.sc_shell)
                except Exception:
                    pass
            self.sc_shell.bypass_login = prior_bypass

    def _dump_uart(self, console, phase, attempt):
        if not self.debug_write_boot_log:
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

    def _select_update_path(self):
        """Validate optional bindings against requested update flags. Return path tag."""
        if self.update_image and not (self.image_writer and self.sdmux and self.kuiper):
            raise StrategyError("update_image=True requires image_writer + sdmux + kuiper bindings")

        if not self.update_boot_files:
            return None

        if not self.kuiper:
            raise StrategyError(
                "update_boot_files=True requires the kuiper binding to source files"
            )

        if self.sdmux and self.mass_storage:
            return "sdmux"
        if self.ssh:
            return "ssh"
        raise StrategyError(
            "update_boot_files=True needs either (sdmux + mass_storage) or an ssh binding"
        )

    def _stage_files_via_sdmux(self):
        """SD-mux flow: mux to host, optionally write image, copy boot files, unmount."""
        if self.image_writer and self.update_image:
            self.logger.info("Writing full Kuiper image to SD card (this may take minutes)...")
            self.target.activate(self.image_writer)
            from labgrid.driver.usbstoragedriver import Mode

            self.image_writer.write_image(mode=Mode.BMAPTOOL)
            self.target.deactivate(self.image_writer)
            self.logger.info("Image written")

        self.logger.info("Updating boot files on SD card via SD-mux...")
        self.target.activate(self.mass_storage)
        self.mass_storage.mount_partition()
        for boot_file in self.kuiper._boot_files:
            self.logger.info("Copying %s to SD card...", boot_file)
            self.mass_storage.copy_file(boot_file, "/")
        self.mass_storage.unmount_partition()
        self.target.deactivate(self.mass_storage)
        self.logger.info("Boot files updated via SD-mux")

    def _stage_files_via_ssh(self):
        """SSH flow: scp boot files into the Versal's boot partition, sync, reboot.

        Caller relies on the next ``Status.booting`` cold-cycle to actually
        bring the board up cleanly — we don't trust graceful reboot to land
        on a system whose only purpose is to get re-imaged.
        """
        self.logger.info("Updating boot files on Versal via SSH...")
        self.target.activate(self.ssh)
        try:
            for boot_file in self.kuiper._boot_files:
                self.logger.info("scp %s -> %s/", boot_file, self.boot_partition_path)
                self.ssh.put(boot_file, f"{self.boot_partition_path}/")
            self.ssh.run_check("sync")
            try:
                self.ssh.run(self.ssh_reboot_command)
            except Exception as e:
                self.logger.debug("SSH reboot command exited (expected): %s", e)
        finally:
            try:
                self.target.deactivate(self.ssh)
            except Exception:
                pass
        self.logger.info("Boot files updated via SSH")

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

    def _run_sc_commands(self):
        """Run configured sc_commands in order. On failure cold-cycle and restart phase."""
        if not self.sc_commands:
            self.logger.info("No SC commands configured; SC alive is sufficient.")
            return

        attempt = 0
        max_attempts = int(self.sc_command_retries) + 1
        while True:
            attempt += 1
            try:
                for cmd in self.sc_commands:
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

    def _wait_for_versal_kernel(self):
        """Watch the Versal UART for the kernel banner. Retry on zero-byte silence."""
        self.target_shell.bypass_login = True
        self.target.activate(self.target_shell)

        attempt = 0
        max_attempts = int(self.kernel_banner_retries) + 1
        while True:
            attempt += 1
            try:
                _, before, _, _ = self.target_shell.console.expect(
                    self.kernel_banner_pattern,
                    timeout=self.wait_for_kernel_banner_timeout,
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
                self._dump_uart(self.target_shell.console, "versal_banner", attempt)
                self.logger.error(
                    "Attempt %d/%d: no Versal 'Linux' banner within %ss (%d bytes captured).",
                    attempt,
                    max_attempts,
                    self.wait_for_kernel_banner_timeout,
                    len(captured),
                )
                if captured:
                    self.logger.error("Captured Versal UART tail: %r", captured[-400:])
                # Versal SD boot is expected to reach Linux under normal
                # operation; any timeout (silent OR stuck-at-U-Boot-prompt)
                # is a candidate for cold-cycle recovery. Bail only when
                # retries are exhausted.
                if attempt >= max_attempts:
                    raise e
                self.logger.info("Cold-cycling, redoing SC phase, re-watching Versal UART.")
                self.target.deactivate(self.target_shell)
                self._cold_cycle()
                self._wait_for_sc_alive()
                self._run_sc_commands()
                self.target_shell.bypass_login = True
                self.target.activate(self.target_shell)

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Drive the state machine toward ``status``.

        States are walked in order; requesting ``shell`` will transition through
        every prior state needed. Mirrors ``BootFPGASoC.transition``.
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
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Board powered off")

        elif status == Status.sd_mux_to_host:
            if not self.sdmux:
                raise StrategyError("sd_mux_to_host requires sdmux binding")
            self.transition(Status.powered_off)
            self.target.activate(self.sdmux)
            self.logger.info("Muxing SD card to host...")
            self.sdmux.set_mode("host")
            time.sleep(5)
            self.logger.info("SD card muxed to host")

        elif status == Status.update_boot_files:
            path = self._select_update_path()
            if path is None:
                self.logger.info("update_boot_files=False; skipping file staging")
            elif path == "sdmux":
                self.transition(Status.sd_mux_to_host)
                self._stage_files_via_sdmux()
            elif path == "ssh":
                self._stage_files_via_ssh()

        elif status == Status.sd_mux_to_dut:
            if not self.sdmux:
                raise StrategyError("sd_mux_to_dut requires sdmux binding")
            self.transition(Status.update_boot_files)
            self.logger.info("Muxing SD card back to DUT...")
            self.sdmux.set_mode("dut")
            time.sleep(5)
            self.logger.info("SD card muxed to DUT")

        elif status == Status.booting:
            # Warm-boot fast path: if SC is already responsive AND no
            # file-update is requested, skip the cold-cycle and rely on
            # `sc_app -c reset` (in sc_commands) to restart just the Versal
            # target. Saves ~75-90s and avoids the SC-wedge mode caused by
            # repeated power cycling. File-update flows must still go through
            # powered_off → SD-mux/SSH → cold-cycle.
            needs_file_update = self.update_boot_files or self.update_image
            if self.warm_boot_if_sc_alive and not needs_file_update and self._sc_appears_alive():
                self.logger.info("SC is already responsive — skipping cold-cycle (warm boot path).")
                self.target.activate(self.power)
                self.power.on()
                self.status = status
                return

            if self.sdmux:
                self.transition(Status.sd_mux_to_dut)
            else:
                self.transition(Status.update_boot_files)
            self.target.activate(self.power)
            self.logger.info("Cold-cycling power before SC orchestration...")
            self.power.off()
            time.sleep(5)
            self.power.on()
            self.logger.info("Board powered on, awaiting SC.")

        elif status == Status.booted:
            self.transition(Status.booting)
            self.boot_log = ""
            self._wait_for_sc_alive()
            self._run_sc_commands()
            self.target.deactivate(self.sc_shell)
            self._wait_for_versal_kernel()

            try:
                _, before, _, _ = self.target_shell.console.expect(
                    self.reached_linux_marker, timeout=self.wait_for_linux_prompt_timeout
                )
                if before:
                    self.boot_log += before.decode("utf-8", errors="replace")
            except Exception:
                self._dump_uart(self.target_shell.console, "versal_prompt", 1)
                raise

            self.target_shell.bypass_login = False
            self.target.deactivate(self.target_shell)
            self.logger.info("Versal booted to '%s'", self.reached_linux_marker)

        elif status == Status.shell:
            self.transition(Status.booted)
            self.logger.info("Preparing interactive shell...")
            self.target.activate(self.target_shell)
            self.logger.info("Shell access ready")

        elif status == Status.soft_off:
            try:
                self.target.activate(self.target_shell)
                self.target_shell.console.sendline("poweroff")
                self.target_shell.console.expect(".*Power down.*", timeout=30)
                self.target.deactivate(self.target_shell)
                time.sleep(10)
            except Exception as e:
                self.logger.debug("Soft-off via Versal failed: %s", e)
                time.sleep(5)
                try:
                    self.target.deactivate(self.target_shell)
                except Exception:
                    pass
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Board hard powered off after soft-off attempt")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
