import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError

from ._compat import never_retry


class Status(enum.Enum):
    """Boot strategy state machine states.

    Attributes:
        unknown: Initial state before any operations.
        powered_off: Device is powered off.
        sd_mux_to_host: SD card muxed to host for file operations.
        update_boot_files: Copying boot files to SD card.
        sd_mux_to_dut: SD card muxed to device for booting.
        booting: Device powered on, boot in progress.
        booted: Linux kernel has booted, waiting for user space.
        shell: Interactive shell session available.
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
class BootFPGASoC(Strategy):
    """BootFPGASoC strategy for FPGA SoC devices using Kuiper releases.

    This strategy works by using an SD card mux to flash a Kuiper release image
    onto the device's SD card, and move the necessary boot files into the
    appropriate locations before booting the device. Flashing a full image
    is set through the `update_image` attribute. The following bindings must be
    present on the target:
    - PowerProtocol (any power control protocol)
    - SDMuxDriver (to switch SD card between host and DUT)
    - MassStorageDriver (to copy boot files to the SD card)
    - ADIShellDriver (to interact with the device shell after boot)
    - KuiperDLDriver (to download and manage Kuiper release files)

    Optionally, an ImageWriter driver can be used to flash the full image.
    This is controlled by the `update_image` attribute.

    Therefore, physical connections must be set up to allow:
    - Power control of the device
    - SD card access from the host (via SD mux)
    - Shell access to the device (e.g., via serial console)

    Args:
        reached_linux_marker (str): String to expect in the shell to confirm Linux has booted.
        update_image (bool): Whether to flash the full Kuiper image to the SD card.
        wait_for_linux_prompt_timeout (int): Timeout in seconds to wait for Linux prompt after boot.
    """

    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "sdmux": "USBSDMuxDriver",
        "mass_storage": "MassStorageDriver",
        "image_writer": {"USBStorageDriver", None},
        "kuiper": {"KuiperDLDriver", "CloudsmithDLDriver"},
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    update_image = attr.ib(default=False)
    wait_for_linux_prompt_timeout = attr.ib(default=60)
    # How long to wait, after power-on, for the first "Linux" banner
    # from U-Boot/kernel.  A tight default (30 s) was a common source
    # of flake on slow SD cards where FSBL+U-Boot+kernel load takes
    # more than half a minute.
    wait_for_kernel_banner_timeout = attr.ib(default=120)
    # If the banner expect times out with zero bytes on the serial
    # (board didn't actually power on, ser2net stuck on a stale
    # session, FAT write didn't flush, etc.), power-cycle and try
    # again this many times before giving up.  One retry is enough
    # to catch typical flakes without masking real failures.
    kernel_banner_retries = attr.ib(default=1)
    boot_log = attr.ib(default="", init=False)

    debug_write_boot_log = attr.ib(default=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootFPGASoC strategy initialized")
        if self.kuiper:
            self.logger.info("Preloading Kuiper boot files")
            self.target.activate(self.kuiper)
            self.kuiper.get_boot_files_from_release()
            self.target.deactivate(self.kuiper)

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        This method manages state transitions for the boot process. It handles
        power control, SD mux switching, boot file updates, and device activation
        in the correct sequence.

        Args:
            status (Status or str): Target state to transition to. Can be a Status enum
                value or its string representation (e.g., "shell", "booted").
            step: Labgrid step decorator context (injected automatically).

        Raises:
            StrategyError: If the transition is invalid or fails.

        Example:
            >>> strategy.transition("shell")  # Transition to shell state
            >>> strategy.transition(Status.soft_off)  # Power off the device

        Note:
            State transitions are sequential. Requesting a state that requires
            intermediate states will automatically transition through them.
        """
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Existing status: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return  # nothing to do
        elif status == Status.powered_off:
            self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")
        elif status == Status.sd_mux_to_host:
            self.transition(Status.powered_off)
            self.target.activate(self.sdmux)
            self.logger.info("Muxing SD card to host...")
            self.sdmux.set_mode("host")
            time.sleep(5)
            self.logger.info("SD card muxed to host")
        elif status == Status.update_boot_files:
            self.transition(Status.sd_mux_to_host)
            if self.image_writer and self.update_image:
                self.logger.info(
                    "Writing full Kuiper image to SD card (this may take several minutes)..."
                )
                self.target.activate(self.image_writer)
                from labgrid.driver.usbstoragedriver import Mode

                self.image_writer.write_image(mode=Mode.BMAPTOOL)
                # self.image_writer.write_image()
                self.target.deactivate(self.image_writer)
                self.logger.info("Image written successfully")

            self.logger.info("Updating boot files on SD card...")
            self.target.activate(self.mass_storage)
            self.mass_storage.mount_partition()
            for boot_file in self.kuiper._boot_files:
                self.logger.info(f"Copying {boot_file} to SD card...")
                self.mass_storage.copy_file(boot_file, "/")
            self.mass_storage.unmount_partition()
            self.target.deactivate(self.mass_storage)
            self.logger.info("Boot files updated successfully")

        elif status == Status.sd_mux_to_dut:
            self.transition(Status.update_boot_files)
            self.logger.info("Muxing SD card back to DUT...")
            self.sdmux.set_mode("dut")
            time.sleep(5)
            self.logger.info("SD card muxed to DUT")

        elif status == Status.booting:
            self.transition(Status.sd_mux_to_dut)
            self.target.activate(self.power)
            # Explicit off → settle → on sequence.  The prior
            # powered_off transition already toggled power.off(), but
            # the subsequent SD-mux operations take long enough (and
            # the sdmux briefly energizes the SD slot from the host
            # side) that the board can latch into a weird power state
            # where the first `on()` looks applied but the board
            # emits zero UART for 2+ minutes.  Forcing another clean
            # off/on cycle right before the boot window is reliable
            # and shaves ~120 s per run compared to relying on the
            # kernel-banner retry to catch this after the fact.
            self.logger.info("Cold-cycling power to clear residual board state...")
            self.power.off()
            time.sleep(5)
            self.power.on()
            self.logger.info("Device powered on, booting...")

        elif status == Status.booted:
            self.transition(Status.booting)
            self.boot_log = ""  # Reset boot log for this boot
            self.logger.info(f"Waiting for Linux boot and '{self.reached_linux_marker}' prompt...")
            self.shell.bypass_login = True
            self.target.activate(self.shell)

            # Check kernel start.  If the board is silent during this
            # window the problem is almost always FSBL/BOOT.BIN or the
            # serial exporter, not a slow kernel — surface the captured
            # UART buffer so we can tell which.  Retry the power-cycle
            # once if the board is *completely* silent, which catches
            # the common flake mode where the previous run left a
            # stale ser2net session or the FAT write didn't flush.
            before = b""
            attempt = 0
            max_attempts = int(self.kernel_banner_retries) + 1
            while True:
                attempt += 1
                try:
                    _, before, _, _ = self.shell.console.expect(
                        "Linux", timeout=self.wait_for_kernel_banner_timeout
                    )
                    break
                except Exception as e:
                    captured = b""
                    try:
                        captured = self.shell.console._expect.before or b""
                    except Exception:
                        pass
                    if self.debug_write_boot_log:
                        uart_log_filename = (
                            f"uart_log_kernel_banner_attempt{attempt}_{int(time.time())}.txt"
                        )
                        with open(uart_log_filename, "wb") as f:
                            f.write(captured)
                        self.logger.info(f"Wrote log file to {uart_log_filename}")
                    self.logger.error(
                        "Attempt %d/%d: no 'Linux' banner within %ss (%d bytes captured).",
                        attempt,
                        max_attempts,
                        self.wait_for_kernel_banner_timeout,
                        len(captured),
                    )
                    if captured:
                        self.logger.error("Captured UART tail: %r", captured[-400:])
                    # Only retry on zero-byte silence; if the board
                    # produced *some* output we're looking at a real
                    # boot problem that another power-cycle won't fix.
                    if attempt >= max_attempts or len(captured) > 0:
                        raise e
                    self.logger.info(
                        "Power-cycling the board and re-attempting the kernel banner wait."
                    )
                    self.target.deactivate(self.shell)
                    self.target.activate(self.power)
                    self.power.off()
                    time.sleep(5)
                    self.power.on()
                    self.logger.info("Device re-powered, booting...")
                    # Re-activate the shell driver so we get a fresh
                    # serial reader thread on the retry.
                    self.shell.bypass_login = True
                    self.target.activate(self.shell)

            if before:
                self.boot_log += before.decode("utf-8", errors="replace")
            # Check device prompt
            try:
                _, before, _, _ = self.shell.console.expect(
                    self.reached_linux_marker, timeout=self.wait_for_linux_prompt_timeout
                )  # Adjust prompt as needed
            except Exception as e:
                if self.debug_write_boot_log:
                    uart_log_filename = f"uart_log_{int(time.time())}.txt"
                    with open(uart_log_filename, "wb") as f:
                        f.write(self.shell.console._expect.before)
                        self.logger.info(f"Wrote log file to {uart_log_filename}")
                raise e
            if before:
                self.boot_log += before.decode("utf-8", errors="replace")
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.info("Device booted successfully")

        elif status == Status.shell:
            self.transition(Status.booted)
            # self.shell.bypass_login = True
            self.logger.info("Preparing interactive shell...")
            self.target.activate(self.shell)
            # Post boot stuff...
            self.logger.info("Shell access ready")

        elif status == Status.soft_off:
            # Stage is relatively standalone
            try:
                self.activate(self.shell)
                self.shell.sendline("poweroff")
                self.shell.console.expect(".*Power down.*", timeout=30)
                self.target.deactivate(self.shell)
                time.sleep(10)
            except Exception as e:
                self.logger.debug(f"DEBUG Soft off failed: {e}")
                time.sleep(5)
                self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            self.logger.debug("DEBUG Soft powered off")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
