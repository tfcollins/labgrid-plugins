"""Strategy to manage Raspberry Pi devices via SSH with optional power, serial, and SD mux."""

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """State machine states for RPI management.

    Attributes:
        unknown: Initial state before any operations.
        off: Device is powered off or assumed off.
        booting: Device is powering on, waiting for SSH connectivity.
        booted: SSH is reachable.
        shell: SSH session active, ready for commands and file transfer.
        soft_off: Device being shut down gracefully.
    """

    unknown = 0
    off = 1
    booting = 2
    booted = 3
    shell = 4
    soft_off = 5


@target_factory.reg_driver
@attr.s(eq=False)
class BootRPI(Strategy):
    """Strategy to manage Raspberry Pi devices primarily via SSH.

    This strategy manages Raspberry Pi devices using SSH as the primary
    interface. Power control, serial console, and SD card mux are optional.

    When multiple control methods are available, the strategy uses a cascading
    priority for reboot/shutdown operations:
        1. Power driver (hard reset via smart outlet/PDU)
        2. Serial console (reboot/poweroff command via ADIShellDriver)
        3. SSH (reboot/poweroff command via SSHDriver)

    Bindings:
        ssh: SSHDriver (required) - Primary interface for commands and file transfer
        power: PowerProtocol (optional) - Hardware power control
        shell: ADIShellDriver (optional) - Serial console access
        sdmux: USBSDMuxDriver (optional) - SD card mux control

    Attributes:
        ssh_boot_timeout: Seconds to wait for SSH connectivity after boot. Default: 120.
        power_off_delay: Seconds to wait after power off before power on. Default: 2.
    """

    bindings = {
        "ssh": "SSHDriver",
        "power": {"PowerProtocol", None},
        "shell": {"ADIShellDriver", None},
        "sdmux": {"USBSDMuxDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    ssh_boot_timeout = attr.ib(
        default=120,
        validator=attr.validators.instance_of(int),
    )
    power_off_delay = attr.ib(
        default=2,
        validator=attr.validators.instance_of(int),
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootRPI strategy initialized")

    def _power_off(self):
        """Shut down the device using the best available method.

        Priority: power driver > serial console > SSH.
        """
        if self.power:
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off via power driver")
        elif self.shell:
            try:
                self.target.activate(self.shell)
                self.shell.run("poweroff")
                self.target.deactivate(self.shell)
            except Exception as e:
                self.logger.debug(f"Shell poweroff exception (expected): {e}")
            self.logger.info("Device powered off via serial console")
        else:
            try:
                self.target.activate(self.ssh)
                self.ssh.run("sudo poweroff")
                self.target.deactivate(self.ssh)
            except Exception as e:
                self.logger.debug(f"SSH poweroff exception (expected): {e}")
            self.logger.info("Device powered off via SSH")

    def _power_on(self):
        """Power on or reboot the device using the best available method.

        Priority: power driver > serial console > SSH.

        With power driver: hard power on.
        Without power driver: assumes device is reachable and issues reboot.
        """
        if self.power:
            self.target.activate(self.power)
            self.power.on()
            self.logger.info("Device powered on via power driver")
        elif self.shell:
            try:
                self.target.activate(self.shell)
                self.shell.run("reboot")
                self.target.deactivate(self.shell)
            except Exception as e:
                self.logger.debug(f"Shell reboot exception (expected): {e}")
            self.logger.info("Reboot issued via serial console")
        else:
            try:
                self.target.activate(self.ssh)
                self.ssh.run("sudo reboot")
                self.target.deactivate(self.ssh)
            except Exception as e:
                self.logger.debug(f"SSH reboot exception (expected): {e}")
            self.logger.info("Reboot issued via SSH")

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        Manages state transitions for RPI management. Handles power control,
        SSH connectivity, and graceful shutdown using cascading driver priority.

        Args:
            status (Status or str): Target state to transition to. Can be a Status enum
                value or its string representation (e.g., "shell", "off").
            step: Labgrid step decorator context (injected automatically).

        Raises:
            StrategyError: If the transition is invalid or fails.
        """
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Current: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return

        elif status == Status.off:
            # Deactivate any active drivers
            self.target.deactivate(self.ssh)
            if self.shell:
                self.target.deactivate(self.shell)
            self._power_off()

        elif status == Status.booting:
            self.transition(Status.off)
            time.sleep(self.power_off_delay)
            self._power_on()
            self.logger.info("Device booting...")

        elif status == Status.booted:
            if self.power or self.status != Status.unknown:
                # Full reboot cycle if we have power control or are in a known state
                self.transition(Status.booting)
            else:
                # No power driver and unknown state: device is presumably already running
                self.logger.info("No power driver, assuming device is already running")
            self.logger.info(f"Waiting for SSH connectivity (timeout: {self.ssh_boot_timeout}s)...")
            deadline = time.time() + self.ssh_boot_timeout
            while time.time() < deadline:
                try:
                    self.target.activate(self.ssh)
                    self.logger.info("SSH connection established")
                    break
                except Exception:
                    self.target.deactivate(self.ssh)
                    time.sleep(5)
            else:
                raise StrategyError(f"SSH connection failed after {self.ssh_boot_timeout}s timeout")

        elif status == Status.shell:
            self.transition(Status.booted)
            self.logger.info("SSH shell ready for commands and file transfer")

        elif status == Status.soft_off:
            self._power_off()
            if self.power:
                self.target.deactivate(self.power)
            self.logger.info("Device shut down gracefully")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
