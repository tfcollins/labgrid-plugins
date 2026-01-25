"""Strategy to boot logic-only Xilinx FPGAs (Virtex/Artix/Kintex) with Microblaze."""

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for Virtex/Artix FPGA boot.

    Attributes:
        unknown: Initial state before any operations.
        powered_off: FPGA is powered off.
        powered_on: FPGA is powered on but not configured.
        bitstream_flashed: FPGA bitstream has been flashed via JTAG.
        kernel_downloaded: Linux kernel has been downloaded to Microblaze.
        booting: Kernel execution has started.
        booted: Kernel has booted and is ready for interaction.
        shell: Interactive shell session available on Microblaze.
        soft_off: Device being shut down gracefully.
    """

    unknown = 0
    powered_off = 1
    powered_on = 2
    flash_fpga = 3
    booted = 4
    shell = 5
    soft_off = 6


@target_factory.reg_driver
@attr.s(eq=False)
class BootFabric(Strategy):
    """BootFabric - Strategy to boot logic-only Xilinx FPGAs with Microblaze.

    This strategy manages the boot process of logic-only FPGA devices
    (Virtex, Artix, Kintex) using JTAG. It handles powering on the device,
    flashing the bitstream via JTAG, downloading the Linux kernel, and
    providing shell access via serial console.

    Boot Sequence:
        1. Power on FPGA
        2. Flash bitstream via JTAG (configures FPGA fabric and Microblaze processor)
        3. Download Linux kernel image via JTAG
        4. Start kernel execution
        5. Wait for boot completion and verify shell access
        6. Provide interactive shell access

    Bindings:
        power: PowerProtocol (optional) - Power control (on/off)
        jtag: XilinxJTAGDriver - JTAG programming driver
        shell: ADIShellDriver (optional) - Serial console access

    Resources:
        XilinxDeviceJTAG: JTAG target IDs and file paths
        XilinxVivadoTool: Vivado installation path for xsdb

    Attributes:
        reached_boot_marker (str): String to expect in console when boot complete.
            Default: "login:" (standard Linux login prompt).
        wait_for_boot_timeout (int): Timeout in seconds to wait for boot marker.
            Default: 120 seconds.
        verify_iio_device (str, optional): IIO device name to verify after boot.
            If specified, driver checks if device is available after booting.
            Example: "axi-ad9081-rx-hpc" for AD9081 transceiver.
    """

    bindings = {
        "power": {"PowerProtocol", None},
        "jtag": "XilinxJTAGDriver",
        "shell": {"ADIShellDriver", None},  # Optional serial console
    }

    status = attr.ib(default=Status.unknown)

    reached_boot_marker = attr.ib(
        default="login:",
        validator=attr.validators.instance_of(str),
    )
    wait_for_boot_timeout = attr.ib(
        default=120,
        validator=attr.validators.instance_of(int),
    )
    verify_iio_device = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    def __attrs_post_init__(self):
        """Initialize strategy."""
        super().__attrs_post_init__()
        self.logger.info("BootFabric strategy initialized")

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        This method manages state transitions for Virtex/Artix FPGA boot via JTAG.
        It handles power control, bitstream flashing, kernel downloading, and boot
        verification.

        Args:
            status (Status or str): Target state to transition to. Can be a Status enum
                value or its string representation (e.g., "shell", "booted").
            step: Labgrid step decorator context (injected automatically).

        Raises:
            StrategyError: If the transition is invalid or fails.

        Example:
            >>> strategy.transition("shell")  # Boot FPGA and get shell
            >>> strategy.transition("soft_off")  # Power off FPGA

        Note:
            State transitions are sequential. Requesting a state that requires
            intermediate states will automatically transition through them.
        """
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.debug(f"Transitioning to {status} (Current: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"Cannot transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return

        elif status == Status.powered_off:
            # Deactivate shell if active
            if self.shell:
                self.target.deactivate(self.shell)
            # Power off FPGA
            if self.power:
                self.target.activate(self.power)
                self.power.off()
                self.logger.info("FPGA powered off")
            else:
                self.logger.info("Skipping power off (no power resource configured)")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            if self.power:
                self.target.activate(self.power)
                time.sleep(2)
                self.power.on()
                time.sleep(5)  # Wait for power stabilization
                self.logger.info("FPGA powered on")
            else:
                self.logger.info("Skipping power on (no power resource configured)")

        elif status == Status.flash_fpga:
            self.transition(Status.powered_on)
            self.target.activate(self.jtag)
            self.jtag.load_bitstream_and_kernel_and_start()
            self.logger.info("Bitstream flashed and kernel started via JTAG")

        # elif status == Status.bitstream_flashed:
        #     self.transition(Status.powered_on)
        #     self.target.activate(self.jtag)
        #     self.jtag.flash_bitstream()
        #     self.logger.info("Bitstream flashed via JTAG")

        # elif status == Status.kernel_downloaded:
        #     self.transition(Status.bitstream_flashed)
        #     self.jtag.download_kernel()
        #     self.logger.info("Kernel downloaded to Microblaze")

        # elif status == Status.booting:
        #     self.transition(Status.kernel_downloaded)
        #     self.jtag.start_execution()
        #     self.jtag.disconnect_jtag()
        #     self.target.deactivate(self.jtag)
        #     self.logger.info("Kernel execution started")

        elif status == Status.booted:
            # self.transition(Status.booting)
            self.transition(Status.flash_fpga)
            if self.shell:
                self.shell.bypass_login = True
                self.target.activate(self.shell)
                # Wait for Linux kernel boot
                self.shell.console.expect("Linux", timeout=30)
                # Wait for login prompt or marker
                self.shell.console.expect(
                    self.reached_boot_marker, timeout=self.wait_for_boot_timeout
                )
                self.shell.bypass_login = False
                self.target.deactivate(self.shell)
                self.logger.info("Microblaze kernel booted")
            else:
                # No shell configured, just wait
                time.sleep(self.wait_for_boot_timeout)
                self.logger.info("Assumed booted (no shell verification)")

        elif status == Status.shell:
            self.transition(Status.booted)
            if self.shell:
                self.target.activate(self.shell)
                # Optional: Verify IIO device if configured
                if self.verify_iio_device:
                    self._verify_iio_device()
                self.logger.info("Shell access ready")
            else:
                raise StrategyError("Shell access requested but no shell driver configured")

        elif status == Status.soft_off:
            # Graceful shutdown if shell available
            if self.shell:
                try:
                    self.target.activate(self.shell)
                    self.shell.run("poweroff")
                    self.shell.console.expect("Power down", timeout=30)
                    self.target.deactivate(self.shell)
                    time.sleep(10)
                except Exception as e:
                    self.logger.warning(f"Graceful shutdown failed: {e}")
                    self.target.deactivate(self.shell)
            # Hard power off
            self.transition(Status.powered_off)
            if self.power:
                self.logger.info("FPGA shut down")

        else:
            raise StrategyError(f"No transition found from {self.status} to {status}")

        self.status = status

    def _verify_iio_device(self):
        """Verify IIO device is available after boot.

        Polls the IIO device for up to 30 seconds, checking if the device
        becomes available after boot.

        Raises:
            StrategyError: If device is not found within timeout.
        """
        self.logger.info(f"Verifying IIO device: {self.verify_iio_device}")
        for _attempt in range(30):
            stdout, stderr, returncode = self.shell.run(
                f"iio_attr -d {self.verify_iio_device} name",
                timeout=5,
            )
            if returncode == 0 and "could not find device" not in stdout:
                self.logger.info(f"IIO device {self.verify_iio_device} found and ready")
                return
            time.sleep(1)
        raise StrategyError(f"IIO device {self.verify_iio_device} not found after boot")
