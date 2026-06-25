"""Driver to load/unload the Tick kernel module and expose its IIO device.

Stages the ``.ko`` on the target, checks vermagic against the running kernel,
``insmod``s it (with an optional ``force`` fallback), and optionally restarts
``iiod`` so the network IIO context re-enumerates the new device.
"""

import os
import shlex

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text


@target_factory.reg_driver
@attr.s(eq=False)
class TickModuleDriver(Driver):
    """Insert/remove ``axi_timed_command_scheduler.ko`` over SSH."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": {"TickArtifacts"},
    }

    restart_iiod = attr.ib(default=True, validator=attr.validators.instance_of(bool))
    force_on_vermagic_mismatch = attr.ib(default=True, validator=attr.validators.instance_of(bool))

    def _modname(self):
        return os.path.basename(self.artifacts.module_ko_path).removesuffix(".ko")

    def load(self):
        """Stage and insmod the module; optionally restart iiod."""
        a = self.artifacts
        ko = f"{a.remote_dir}/{os.path.basename(a.module_ko_path)}"
        self.command.run_check(f"mkdir -p {shlex.quote(a.remote_dir)}")
        self.fs.put(a.module_ko_path, ko)

        vermagic = stdout_text(
            self.command.run_check(f"modinfo -F vermagic {shlex.quote(ko)}")
        ).split()
        krel = stdout_text(self.command.run_check("uname -r")).strip()
        first = vermagic[0] if vermagic else ""
        if first and krel and first != krel:
            self.logger.warning("module vermagic %r != target kernel %r", first, krel)

        # best-effort if already loaded
        self.command.run(f"rmmod {shlex.quote(self._modname())}")
        _stdout, stderr, rc = self.command.run(f"insmod {shlex.quote(ko)}")
        if rc != 0:
            if self.force_on_vermagic_mismatch:
                self.command.run_check(f"insmod {shlex.quote(ko)} force=y")
            else:
                raise ExecutionError(f"insmod failed (rc={rc}): {stderr!r}")

        if self.restart_iiod:
            self.command.run_check("systemctl restart iiod")

    def unload(self):
        """Remove the module (idempotent; used on teardown)."""
        self.command.run(f"rmmod {shlex.quote(self._modname())}")
