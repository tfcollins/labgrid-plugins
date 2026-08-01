"""Strategy to JTAG-boot an UltraScale+ (ZynqMP) board.

This is the UltraScale+ counterpart of ``BootZynq7000JTAGRecovery``. It brings a
ZynqMP board up over JTAG using the Xilinx "mini" U-Boot SPL, which runs
standalone in OCM at EL3 -- **no ARM Trusted Firmware, no PMU firmware** -- and
exposes an ARM DCC / JTAG-UART console readable directly by xsdb.

Why this is needed (and different from Zynq-7000):

- A ZynqMP board strapped for **JTAG boot** reads ``BOOT_MODE_USER == 0x0``.
  In that mode the BootROM does not load PMU firmware and the MicroBlaze PMU is
  not exposed as a JTAG debug target.
- Xilinx ATF (BL31) requires PMU-FW; without it BL31 spins forever in
  ``ipi_mb_notify`` waiting on the PMU IPI mailbox, so full U-Boot never runs.
- The ``xilinx_zynqmp_mini_*`` SPL sidesteps all of that: it is a single EL3
  blob that comes up far enough to own the SD host controller, which is exactly
  what SD-card recovery / bring-up needs. See
  ``examples/ultrascale_jtag_boot/`` for how to build the SPL and a working
  per-board YAML.

Caller responsibilities (paths readable by the host that runs xsdb):

- ``psu_init_tcl``: the board's generated ``psu_init.tcl`` (brings up clocks,
  DDR, and the SD MIO mux). Extract it from your HDL project / XSA.
- ``spl_elf``: ``spl/u-boot-spl`` built by
  ``examples/ultrascale_jtag_boot/build-mini-uboot.sh``.
- ``bitstream_path`` (optional): PL bitstream, programmed before ``psu_init``
  when the PS init depends on the PL.

The actual xsdb sequencing lives in
``XilinxJTAGDriver.load_zynqmp_uboot`` so it can be unit-tested and reused
independently of this strategy.
"""

import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """State machine for the ZynqMP JTAG boot flow.

    Attributes:
        unknown: Initial state before any operation.
        powered_off: Board outlet is off.
        powered_on: Board outlet is on (mode pins sampled at POR).
        jtag_bootstrap: Mini U-Boot SPL has been JTAG-loaded and started.
    """

    unknown = 0
    powered_off = 1
    powered_on = 2
    jtag_bootstrap = 3


@target_factory.reg_driver
@attr.s(eq=False)
class BootZynqMPJTAG(Strategy):
    """Bring up a ZynqMP board over JTAG via the mini U-Boot SPL.

    Bindings:
        power: PowerProtocol (managed outlet).
        jtag: XilinxJTAGDriver (runs xsdb locally or on the exporter).

    The optional ``shell`` binding, when present, is deactivated before the
    JTAG bootstrap so it does not hold the serial line; DCC console output is
    captured to ``dcc_log_path`` on the xsdb host instead.
    """

    bindings = {
        "power": "PowerProtocol",
        "jtag": "XilinxJTAGDriver",
        "shell": {"ADIShellDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    # JTAG bootstrap inputs (paths on the host that runs xsdb).
    psu_init_tcl = attr.ib(default=None)
    spl_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)

    # xsdb tuning (see XilinxJTAGDriver.load_zynqmp_uboot).
    a53_target_name = attr.ib(default="*Cortex-A53*#0*")
    apu_release_rst_value = attr.ib(default="0x380E")
    dcc_log_path = attr.ib(default=None)
    spl_settle_ms = attr.ib(default=12000)

    # Timing.
    power_off_settle_s = attr.ib(default=5)
    power_on_settle_s = attr.ib(default=8)

    def _require(self, name):
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"BootZynqMPJTAG requires '{name}' to be set")
        return value

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        Args:
            status (Status or str): target state (enum or its name, e.g.
                ``"jtag_bootstrap"``).
            step: labgrid step context (injected).

        Raises:
            StrategyError: on an invalid transition or missing inputs.

        Example:
            >>> strategy.transition("jtag_bootstrap")
        """
        if not isinstance(status, Status):
            status = Status[status]

        # Validate required inputs up-front, before @never_retry mutates any
        # state, so a missing input raises a clear error and leaves the
        # strategy reusable (rather than wedging it in "broken state").
        if status == Status.jtag_bootstrap:
            self._require("psu_init_tcl")
            self._require("spl_elf")

        self.logger.info(f"Transitioning to {status} (existing: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        elif status == self.status:
            step.skip("nothing to do")
            return

        elif status == Status.powered_off:
            if self.shell:
                self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            time.sleep(self.power_off_settle_s)
            self.logger.info("Board powered off")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            self.power.on()
            time.sleep(self.power_on_settle_s)
            self.logger.info("Board powered on")

        elif status == Status.jtag_bootstrap:
            psu_init_tcl = self._require("psu_init_tcl")
            spl_elf = self._require("spl_elf")
            self.transition(Status.powered_on)
            self.target.activate(self.jtag)
            self.logger.info("JTAG-bootstrapping ZynqMP mini U-Boot SPL...")
            self.jtag.load_zynqmp_uboot(
                psu_init_tcl=psu_init_tcl,
                spl_elf=spl_elf,
                bitstream_path=self.bitstream_path,
                a53_target_name=self.a53_target_name,
                apu_release_rst_value=self.apu_release_rst_value,
                dcc_log_path=self.dcc_log_path,
                settle_ms=self.spl_settle_ms,
            )
            self.logger.info("ZynqMP mini U-Boot SPL bootstrapped via JTAG")

        else:
            raise StrategyError(f"no transition handler for {status}")

        self.status = status
