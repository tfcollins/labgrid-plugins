"""Driver to apply/remove a Tick devicetree overlay via configfs.

Expects a prebuilt ``.dtbo`` (no dtc dependency). Stages it on the target,
ensures configfs is mounted, and applies it under
``/sys/kernel/config/device-tree/overlays/<overlay_name>``.
"""

import shlex

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text

_CONFIGFS = "/sys/kernel/config/device-tree/overlays"


@target_factory.reg_driver
@attr.s(eq=False)
class TickOverlayDriver(Driver):
    """Apply and remove the Tick DT overlay through configfs."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": {"TickArtifacts"},
    }

    def apply(self):
        """Stage the .dtbo and apply the overlay; raise unless it reports applied."""
        a = self.artifacts
        remote = f"{a.remote_dir}/{a.overlay_name}.dtbo"
        ovl = f"{_CONFIGFS}/{a.overlay_name}"
        self.command.run_check(f"mkdir -p {shlex.quote(a.remote_dir)}")
        self.fs.put(a.overlay_dtbo_path, remote)
        self.command.run_check(
            "sh -c 'mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config'"
        )
        self.command.run(f"rmdir {shlex.quote(ovl)}")  # best-effort: clear a stale overlay
        self.command.run_check(f"mkdir -p {shlex.quote(ovl)}")
        self.command.run_check(f"sh -c 'cat {shlex.quote(remote)} > {shlex.quote(ovl)}/dtbo'")
        status = stdout_text(self.command.run_check(f"cat {shlex.quote(ovl)}/status"))
        if status.strip() != "applied":
            raise ExecutionError(f"overlay status not applied: {status!r}")

    def remove(self):
        """Remove the overlay (idempotent; used on teardown)."""
        ovl = f"{_CONFIGFS}/{self.artifacts.overlay_name}"
        self.command.run(f"rmdir {shlex.quote(ovl)}")
