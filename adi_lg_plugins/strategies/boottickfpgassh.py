"""Strategy: boot a pre-baked Kuiper SD, then deploy Tick at runtime.

Subclasses BootFPGASoCSSH to reuse its power/boot-to-shell machinery
(``update_image`` stays off so the SD is not rewritten), then adds Tick
deploy states: program the FPGA, apply the DT overlay, and load the kernel
module. Tick states are resolved against this class's own Status enum;
any other value is delegated to the parent state machine.
"""

import enum

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import StrategyError

from ._compat import never_retry
from .bootfpgasocssh import BootFPGASoCSSH


class Status(enum.Enum):
    """Tick deploy states layered on top of BootFPGASoCSSH."""

    unknown = 0
    tick_fpga_loaded = 1
    tick_overlay_applied = 2
    tick_module_loaded = 3
    tick_off = 4


@target_factory.reg_driver
@attr.s(eq=False)
class BootTickFPGASSH(BootFPGASoCSSH):
    """BootFPGASoCSSH + runtime Tick deploy (bitstream, overlay, module)."""

    bindings = {
        **BootFPGASoCSSH.bindings,
        "tick_fpga": "TickFpgaManagerDriver",
        "tick_overlay": "TickOverlayDriver",
        "tick_module": "TickModuleDriver",
    }

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Thin decorated entry point; real logic is in plain helpers (testable)."""
        self._dispatch(status)

    def _dispatch(self, status):
        """Resolve Tick states here; delegate all others to BootFPGASoCSSH."""
        if not isinstance(status, Status):
            try:
                status = Status[status]
            except (KeyError, TypeError):
                return super().transition(status)
        self._transition_tick(status)

    def _transition_tick(self, status):
        if status == self.status:
            return  # already in this Tick state; idempotent, and lets chains resume
        if status == Status.tick_fpga_loaded:
            super().transition("shell")
            self.target.activate(self.tick_fpga)
            self.tick_fpga.load_bitstream()
        elif status == Status.tick_overlay_applied:
            self._transition_tick(Status.tick_fpga_loaded)
            self.target.activate(self.tick_overlay)
            self.tick_overlay.apply()
        elif status == Status.tick_module_loaded:
            self._transition_tick(Status.tick_overlay_applied)
            self.target.activate(self.tick_module)
            self.tick_module.load()
        elif status == Status.tick_off:
            for drv, meth in ((self.tick_module, "unload"), (self.tick_overlay, "remove")):
                try:
                    self.target.activate(drv)
                    getattr(drv, meth)()
                except Exception as exc:  # noqa: BLE001 - best-effort teardown
                    self.logger.debug("tick teardown %s failed: %s", meth, exc)
            if self.power:
                self.target.activate(self.power)
                self.power.off()
        else:
            raise StrategyError(f"unhandled tick status {status}")
        self.status = status
