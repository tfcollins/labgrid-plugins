import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


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
    """

    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "sdmux": "USBSDMuxDriver",
        "mass_storage": "MassStorageDriver",
        "image_writer": {"USBStorageDriver", None},
        "kuiper": "KuiperDLDriver",
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    update_image = attr.ib(default=False)

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

        self.logger.debug(
            f"Transitioning to {status} (Existing status: {self.status}) {status == Status.shell}"
        )

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return  # nothing to do
        elif status == Status.powered_off:
            self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            self.logger.debug("DEBUG Powered off")
        elif status == Status.sd_mux_to_host:
            self.transition(Status.powered_off)
            self.target.activate(self.sdmux)
            self.sdmux.set_mode("host")
            time.sleep(5)
            self.logger.debug("DEBUG SD Mounted")
        elif status == Status.update_boot_files:
            self.transition(Status.sd_mux_to_host)
            if self.image_writer and self.update_image:
                self.logger.info("Writing image to mass storage device")
                self.target.activate(self.image_writer)
                from labgrid.driver.usbstoragedriver import Mode

                self.image_writer.write_image(mode=Mode.BMAPTOOL)
                self.target.deactivate(self.image_writer)
                self.logger.info("Image written successfully")

            self.target.activate(self.mass_storage)
            self.mass_storage.mount_partition()
            for boot_file in self.kuiper._boot_files:
                self.mass_storage.copy_file(boot_file, "/")
            self.mass_storage.unmount_partition()
            self.target.deactivate(self.mass_storage)
            self.logger.debug("DEBUG Boot files updated")

        elif status == Status.sd_mux_to_dut:
            self.transition(Status.update_boot_files)
            self.sdmux.set_mode("dut")
            time.sleep(5)
            self.logger.debug("DEBUG SD Muxed to DUT")

        elif status == Status.booting:
            self.transition(Status.sd_mux_to_dut)
            self.target.activate(self.power)
            time.sleep(5)
            self.power.on()
            self.logger.debug("DEBUG Booting...")

        elif status == Status.booted:
            self.transition(Status.booting)
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            self.shell.console.expect("Linux", timeout=30)
            # Check device prompt
            self.shell.console.expect(
                self.reached_linux_marker, timeout=60
            )  # Adjust prompt as needed
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Booted")

        elif status == Status.shell:
            self.transition(Status.booted)
            # self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Post boot stuff...

        elif status == Status.soft_off:
            self.transition(Status.shell)
            try:
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
