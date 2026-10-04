"""Program FPGA fabric with openFPGALoader through an exported USB probe."""

from __future__ import annotations

import os
import subprocess

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import BootstrapProtocol
from labgrid.step import step

from ._remote import RemoteExecMixin


def _optional_string(_instance, attribute, value):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{attribute.name} must be a string or None")


@target_factory.reg_driver
@attr.s(eq=False)
class OpenFPGALoaderDriver(RemoteExecMixin, Driver, BootstrapProtocol):
    """Load a bitstream using the exact bound USB debugger.

    The driver always selects the exported probe by USB bus/device number (or
    its USB serial when bus/device information is unavailable). Programming is
    volatile SRAM by default. Flash writes require both an explicit method
    argument and ``allow_flash: true`` in the environment.
    """

    bindings = {
        "interface": {
            "USBDebugger",
            "NetworkUSBDebugger",
            "XilinxDeviceJTAG",
        }
    }

    _remote_binding = "interface"

    board = attr.ib(default=None, validator=_optional_string)
    cable = attr.ib(default=None, validator=_optional_string)
    fpga_part = attr.ib(default=None, validator=_optional_string)
    usb_busnum = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    usb_devnum = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    usb_serial = attr.ib(default=None, validator=_optional_string)
    frequency = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(int))
    )
    allow_flash = attr.ib(default=False, converter=bool)
    timeout = attr.ib(default=300, converter=int)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.board = self.board.strip() if self.board else None
        self.cable = self.cable.strip() if self.cable else None
        self.fpga_part = self.fpga_part.strip() if self.fpga_part else None
        self.usb_serial = self.usb_serial.strip() if self.usb_serial else None
        if bool(self.board) == bool(self.cable):
            raise ValueError("configure exactly one of board or cable")
        if self.frequency is not None and self.frequency <= 0:
            raise ValueError("frequency must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.target.env:
            self.tool = self.target.env.config.get_tool("openFPGALoader")
        else:
            self.tool = "openFPGALoader"

    def _probe_args(self) -> list[str]:
        busnum = self.usb_busnum
        devnum = self.usb_devnum
        serial = self.usb_serial
        if busnum is None:
            busnum = getattr(self.interface, "busnum", None)
        if devnum is None:
            devnum = getattr(self.interface, "devnum", None)
        if not serial:
            serial = getattr(self.interface, "serial", None)
        if busnum is not None and devnum is not None:
            selector = ["--busdev-num", f"{int(busnum)}:{int(devnum)}"]
        elif serial:
            selector = ["--usb-serial-num", str(serial)]
        else:
            raise ExecutionError(
                "bound USB debugger has neither bus/device numbers nor a serial; "
                "refusing ambiguous probe selection"
            )

        vendor_id = getattr(self.interface, "vendor_id", None)
        model_id = getattr(self.interface, "model_id", None)
        if vendor_id is not None:
            selector += ["--vid", f"0x{int(vendor_id):04x}"]
        if model_id is not None:
            selector += ["--pid", f"0x{int(model_id):04x}"]
        return selector

    def _base_command(self) -> list[str]:
        command = [self.tool]
        if self.board:
            command += ["--board", self.board]
        else:
            command += ["--cable", self.cable]
        if self.fpga_part:
            command += ["--fpga-part", self.fpga_part]
        if self.frequency is not None:
            command += ["--freq", str(self.frequency)]
        command += self._probe_args()
        return command

    def _run(self, command: list[str]) -> str:
        try:
            result = subprocess.run(
                self._remote_prefix() + command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExecutionError(f"openFPGALoader execution failed: {exc}") from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or "no diagnostic output").strip()
            if len(detail) > 2000:
                detail = detail[-2000:]
            raise ExecutionError(
                f"openFPGALoader failed with exit status {result.returncode}: {detail}"
            )
        return result.stdout

    @Driver.check_active
    @step(args=["filename"])
    def load(self, filename=None):
        """Program ``filename`` into volatile FPGA SRAM."""
        return self.program(filename, write_flash=False)

    @Driver.check_active
    @step(args=["filename", "write_flash"])
    def program(self, filename, *, write_flash=False):
        """Program a bitstream, requiring an explicit opt-in for flash writes."""
        if not filename:
            raise ExecutionError("bitstream filename is required")
        filename = os.fspath(filename)
        if not os.path.isfile(filename):
            raise ExecutionError(f"bitstream does not exist: {filename}")
        if write_flash and not self.allow_flash:
            raise ExecutionError("flash programming is disabled; set allow_flash: true explicitly")

        try:
            staged = self._stage_file(os.path.abspath(filename))
            mode = "--write-flash" if write_flash else "--write-sram"
            command = self._base_command() + [mode, staged]
            return self._run(command)
        finally:
            self._cleanup_remote_stage()

    @Driver.check_active
    @step()
    def detect(self):
        """Detect the FPGA through the same exact probe selector."""
        return self._run(self._base_command() + ["--detect"])
