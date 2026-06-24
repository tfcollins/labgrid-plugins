"""Driver to program the ZynqMP FPGA at runtime via the fpga_manager sysfs.

The ZynqMP fpga_manager accepts a ``.bit`` and strips the Xilinx header
in-kernel; the firmware loader reads from ``/lib/firmware``. The driver binds
the command + file-transfer protocols and a TickArtifacts resource. The
strategy activates the driver before calling ``load_bitstream``.
"""

import shlex

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text


@target_factory.reg_driver
@attr.s(eq=False)
class TickFpgaManagerDriver(Driver):
    """Load a bitstream through ``/sys/class/fpga_manager/fpga0``."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": {"TickArtifacts"},
    }

    def load_bitstream(self):
        """Stage the bitstream into /lib/firmware and program the FPGA."""
        fw = self.artifacts.firmware_name
        self.fs.put(self.artifacts.bitstream_path, f"/lib/firmware/{fw}")
        qfw = shlex.quote(fw)
        self.command.run_check(f"sh -c 'echo {qfw} > /sys/class/fpga_manager/fpga0/firmware'")
        state = stdout_text(self.command.run_check("cat /sys/class/fpga_manager/fpga0/state"))
        if "operating" not in state:
            raise ExecutionError(f"fpga_manager not operating after load: {state!r}")
