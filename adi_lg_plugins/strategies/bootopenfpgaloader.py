"""Explicit openFPGALoader fabric-programming strategy."""

from __future__ import annotations

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError


class Status(enum.Enum):
    unknown = 0
    powered_off = 1
    powered_on = 2
    programmed = 3
    shell = 4


@target_factory.reg_driver
@attr.s(eq=False)
class BootOpenFPGALoader(Strategy):
    """Power a target, program PL SRAM, and optionally prove serial readiness.

    ``programmed`` means only that openFPGALoader completed successfully. The
    ``shell`` state additionally requires target-visible serial evidence. This
    strategy does not initialize a Zynq PS, DDR, or start software.
    """

    bindings = {
        "power": "PowerProtocol",
        "programmer": "OpenFPGALoaderDriver",
        "shell": {"ADIShellDriver", None},
    }

    status = attr.ib(default=Status.unknown)
    bitstream_path = attr.ib(default=None)
    boot_marker = attr.ib(default=None)
    boot_timeout = attr.ib(default=60, converter=int)
    power_settle_time = attr.ib(default=2, converter=float)

    def _require(self, name):
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"{name} is required for BootOpenFPGALoader")
        return value

    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]
        if status == Status.unknown:
            raise StrategyError("can not transition to unknown")
        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            if self.shell is not None:
                self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
        elif status == Status.powered_on:
            if self.status != Status.powered_off:
                self.transition(Status.powered_off)
            self.power.on()
            time.sleep(self.power_settle_time)
        elif status == Status.programmed:
            self.transition(Status.powered_on)
            bitstream = self._require("bitstream_path")
            self.target.activate(self.programmer)
            self.programmer.load(bitstream)
        elif status == Status.shell:
            self.transition(Status.programmed)
            marker = self._require("boot_marker")
            if self.shell is None:
                raise StrategyError("shell driver is required for target-visible verification")
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            self.shell.console.expect(marker, timeout=self.boot_timeout)
        else:  # pragma: no cover
            raise StrategyError(f"unhandled status {status}")

        self.status = status
