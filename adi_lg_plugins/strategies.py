"""
Example boot strategy for a device with power control.

This demonstrates how to create a strategy in a labgrid plugin.
"""

import enum

import attr

from labgrid.factory import target_factory
from labgrid.strategy import Strategy, StrategyError
from labgrid.step import step


class Status(enum.Enum):
    """Device states for the boot strategy."""
    unknown = 0
    off = 1
    booting = 2
    ready = 3


@target_factory.reg_driver
@attr.s(eq=False)
class ExampleBootStrategy(Strategy):
    """
    Strategy for booting a device using power control.

    This is a simplified example. Real strategies would:
    - Wait for boot completion
    - Check console output for boot messages
    - Handle boot failures and retries
    - Transition through multiple boot stages (bootloader, kernel, userspace)

    States:
        unknown: Initial state
        off: Device is powered off
        booting: Device is powering on and booting
        ready: Device has finished booting and is ready for use
    """

    bindings = {
        "power": "PowerProtocol",  # Any driver implementing PowerProtocol
    }

    status = attr.ib(default=Status.unknown)

    @step()
    def transition(self, status, *, step):  # pylint: disable=redefined-outer-name
        """
        Transition to a new device state.

        Args:
            status: Target state (can be Status enum or string)

        Raises:
            StrategyError: If transition is impossible
        """
        if not isinstance(status, Status):
            status = Status[status]

        if status == Status.unknown:
            raise StrategyError(f"Cannot transition to {status}")

        if status == self.status:
            step.skip("already in target state")
            return

        # Transition to off state
        if status == Status.off:
            self.target.log.info("Transitioning to OFF state")
            self.power.off()
            self.status = Status.off
            return

        # Transition to booting state (requires power on)
        if status == Status.booting:
            self.target.log.info("Transitioning to BOOTING state")

            # Ensure we're off first
            if self.status != Status.off:
                self.transition(Status.off)

            # Power on to start booting
            self.power.on()
            self.status = Status.booting
            return

        # Transition to ready state (requires boot completion)
        if status == Status.ready:
            self.target.log.info("Transitioning to READY state")

            # Ensure we're booting first
            if self.status != Status.booting:
                self.transition(Status.booting)

            # In a real implementation, we would:
            # 1. Wait for console output indicating boot completion
            # 2. Check for specific boot success messages
            # 3. Verify system is responsive
            # 4. Set up any required drivers (shell, SSH, etc.)

            import time
            self.target.log.info("Waiting for boot to complete...")
            time.sleep(2)  # Simulate boot time

            self.status = Status.ready
            self.target.log.info("Device is ready")
            return

        raise StrategyError(f"No transition from {self.status} to {status}")
