"""BootNoOSJTAG: flash + run a no-os bare-metal firmware ELF via JTAG.

Unlike the Kuiper boot strategies, there is no Linux, SD card, or network
libIIO. xsdb loads the optional FPGA bitstream + ``ps7_init`` (both produced
by the no-os build's HDL ``.xsa``), downloads the no-os ``.elf``, and starts
it (``dow`` + ``con``). On-target validation is a serial-console banner
assertion: the firmware prints a known marker (e.g. the IIOD server banner)
which is matched on the UART. no-os has no shell prompt or login, so the bound
``ADIShellDriver`` is used only to *read* the console (login bypassed).

The terminal state is ``shell`` (= firmware running + marker seen + console
ready), matching the request flow's common transition target so the existing
``request()`` orchestration can drive it like any other strategy.
"""

from __future__ import annotations

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError


class Status(enum.Enum):
    """BootNoOSJTAG state machine states."""

    unknown = 0
    powered_off = 1
    powered_on = 2
    # Firmware loaded + running, validation banner seen, console readable.
    shell = 3


@target_factory.reg_driver
@attr.s(eq=False)
class BootNoOSJTAG(Strategy):
    """Load and run a no-os firmware ELF on a Zynq-7000 board via JTAG."""

    bindings = {
        "power": "PowerProtocol",
        "jtag": "XilinxJTAGDriver",
        "shell": "ADIShellDriver",
    }

    status = attr.ib(default=Status.unknown)

    # JTAG load inputs (host paths for xsdb). firmware_elf is required; the
    # bitstream + ps7_init come from the no-os build's .xsa when the design
    # touches FPGA-fabric peripherals.
    firmware_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)
    ps7_init_tcl = attr.ib(default=None)
    a9_target_name = attr.ib(default="*Cortex-A9 MPCore #0")

    # On-target validation: wait for this banner on the serial console.
    boot_marker = attr.ib(default="Running IIOD server")
    boot_timeout = attr.ib(default=60)
    power_settle_time = attr.ib(default=2)

    def _require(self, name: str):
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"{name} is required for BootNoOSJTAG")
        return value

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
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            self.power.on()
            time.sleep(self.power_settle_time)
            self.logger.info("Device powered on")

        elif status == Status.shell:
            self.transition(Status.powered_on)
            firmware_elf = self._require("firmware_elf")
            self.target.activate(self.jtag)
            self.logger.info(f"JTAG-flashing no-os firmware {firmware_elf}")
            self.jtag.load_and_run_elf(
                elf_path=firmware_elf,
                a9_target_name=self.a9_target_name,
                bitstream_path=self.bitstream_path,
                ps7_init_tcl=self.ps7_init_tcl,
            )
            # no-os has no login — only read the console for the banner.
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            self.logger.info(f"Waiting for no-os banner {self.boot_marker!r}...")
            self.shell.console.expect(self.boot_marker, timeout=self.boot_timeout)
            self.logger.info("no-os firmware validated on serial console")

        else:  # pragma: no cover - exhaustive enum
            raise StrategyError(f"unhandled status {status}")

        self.status = status
