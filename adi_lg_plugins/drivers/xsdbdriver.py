"""Xilinx System Debugger (XSDB) driver.

Provides compatibility with upstream labgrid PR #706 and the MLE fork,
while adding support for RemoteExecMixin (running xsdb remotely over SSH on
the exporter or connecting to a remote hw_server via TCP).
"""

from __future__ import annotations

import logging
import os
import subprocess

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import BootstrapProtocol
from labgrid.step import step

from ._remote import RemoteExecMixin


@target_factory.reg_driver
@attr.s(eq=False)
class XSDBDriver(RemoteExecMixin, Driver, BootstrapProtocol):
    """Control Xilinx devices using XSDB / Vivado Hardware Server.

    Compatible with upstream labgrid PR #706 and the MLE fork.

    Bindings:
        interface: XilinxUSBJTAG, NetworkXilinxUSBJTAG, XilinxDeviceJTAG,
                   USBDebugger, or NetworkUSBDebugger.
    """

    bindings = {
        "interface": {
            "XilinxUSBJTAG",
            "NetworkXilinxUSBJTAG",
            "XilinxDeviceJTAG",
            "USBDebugger",
            "NetworkUSBDebugger",
        },
    }

    _remote_binding = "interface"

    bitstream = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger = logging.getLogger(f"{self}({self.target})")
        self.xsdb_bin = "xsdb"
        if hasattr(self.target, "env") and self.target.env:
            self.xsdb_bin = self.target.env.config.get_tool("xsdb") or "xsdb"

    def _exporter_host(self, res):
        if os.environ.get("LG_FORCE_LOCAL_XSDB", "").lower() in ("1", "true", "yes", "on"):
            return None
        return super()._exporter_host(res)

    def _resolve_connect_command(self) -> str:
        """Resolve the Tcl connect command based on agent_url or host."""
        agent_url = getattr(self.interface, "agent_url", "") or ""
        host = getattr(self.interface, "host", "") or ""

        if agent_url:
            parts = agent_url.split(":")
            # If agent_url is 'tcp::3121' and host is known, substitute host
            if len(parts) >= 3 and not parts[1] and host:
                parts[1] = host
                agent_url = ":".join(parts)
            return f"connect -url {agent_url}"
        if host and not self._is_remote:
            return f"connect -url tcp:{host}:3121"
        return "connect"

    @Driver.check_active
    @step(args=["tcl_cmds", "interactive"])
    def run(self, tcl_cmds: list[str], interactive: bool = False) -> str:
        """Run a sequence of Tcl commands in XSDB.

        Connects to the hardware server via agent_url if configured.
        """
        conn_cmd = self._resolve_connect_command()
        cmds = [conn_cmd]

        serial = getattr(self.interface, "serial", "") or ""
        if serial:
            cmds.append(f'catch {{jtag targets -filter {{serial == "{serial}"}}}}')

        cmds.extend(tcl_cmds)
        if not interactive:
            cmds.append("disconnect")

        tcl_script = "; ".join(cmds) + "\n"
        self.logger.debug("Executing XSDB Tcl: %s", tcl_script.strip())

        if self._is_remote and not getattr(self.interface, "agent_url", None):
            # Remote execution over SSH on exporter host
            remote_script = self._stage_file_content(tcl_script, suffix=".tcl")
            cmd = f"{self.xsdb_bin} -quiet -eval {remote_script}"
            res = self._remote_run(cmd)
            if res.returncode != 0:
                raise ExecutionError(
                    f"XSDB command failed with code {res.returncode}: {res.stderr}"
                )
            return res.stdout

        # Local execution on runner machine
        cmd_args = [self.xsdb_bin, "-quiet", "-eval", tcl_script]
        if interactive:
            cmd_args.append("-interactive")

        proc = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ExecutionError(f"XSDB command failed: {proc.stderr.strip()}")
        return proc.stdout

    @Driver.check_active
    @step(args=["filename"])
    def program_bitstream(self, filename: str | None = None) -> None:
        """Program FPGA bitstream using XSDB fpga command."""
        target_file = filename or self.bitstream
        if not target_file:
            # Check if bitstream_path exists on interface (XilinxDeviceJTAG compatibility)
            target_file = getattr(self.interface, "bitstream_path", None)

        if not target_file:
            raise ExecutionError("No bitstream filename provided or configured on driver/resource")

        if hasattr(self.target, "env") and self.target.env:
            target_file = self.target.env.config.get_image_path(target_file)

        if self._is_remote and not getattr(self.interface, "agent_url", None):
            target_file = self._stage_file(os.path.abspath(target_file))

        self.logger.info("Programming bitstream via XSDB: %s", target_file)
        self.run([f"fpga {target_file}"])

    @Driver.check_active
    @step(args=["bootmode"])
    def force_bootmode_reset(self, bootmode: str) -> None:
        """Force SoC bootmode switch and trigger system reset.

        Adopted from the MLE labgrid fork for ZynqMP UltraScale+ PSU control.
        """
        bootmode = bootmode.lower()
        modes = {
            "jtag": "0x0100",
            "sd": "0xE100",
            "qspi": "0x2100",
            "emmc": "0x6100",
            "usb": "0x7100",
        }
        if bootmode not in modes:
            raise KeyError(f"invalid boot mode '{bootmode}', must be one of {list(modes.keys())}")

        mode_val = modes[bootmode]
        self.logger.info("Forcing bootmode '%s' (0x%s) via PSU register", bootmode, mode_val)
        self.run(
            [
                'targets -set -filter {name =~ "*PSU*"}',
                "mwr 0xffca0010 0x0",
                f"mwr 0xff5e0200 {mode_val}",
                "rst -system",
                "after 1000",
                "con",
            ]
        )

    @Driver.check_active
    @step()
    def load_and_run_elf(
        self,
        elf_path: str,
        a9_target_name: str = "*Cortex-A9 MPCore #0",
        bitstream_path: str | None = None,
        ps7_init_tcl: str | None = None,
    ) -> None:
        """Load and run an ELF using XSDB."""
        target_elf = elf_path
        target_bit = bitstream_path
        target_tcl = ps7_init_tcl

        if hasattr(self.target, "env") and self.target.env:
            target_elf = self.target.env.config.get_image_path(target_elf)
            if target_bit:
                target_bit = self.target.env.config.get_image_path(target_bit)
            if target_tcl:
                target_tcl = self.target.env.config.get_image_path(target_tcl)

        if self._is_remote and not getattr(self.interface, "agent_url", None):
            target_elf = self._stage_file(os.path.abspath(target_elf))
            if target_bit:
                target_bit = self._stage_file(os.path.abspath(target_bit))
            if target_tcl:
                target_tcl = self._stage_file(os.path.abspath(target_tcl))

        cmds = [
            f'targets -set -filter {{name =~ "{a9_target_name}"}}',
            "rst -system",
            "after 2000",
        ]
        if target_bit:
            cmds.extend([f"fpga -f {target_bit}", "after 2000"])
        if target_tcl:
            cmds.extend([f"source {target_tcl}", "ps7_init", "ps7_post_config"])
        cmds.extend([f"dow {target_elf}", "con"])
        self.run(cmds)

    @Driver.check_active
    @step(args=["filename"])
    def load(self, filename: str) -> None:
        """Implement BootstrapProtocol.load by programming bitstream or ELF."""
        if filename.endswith(".bit") or filename.endswith(".bin"):
            self.program_bitstream(filename)
        elif filename.endswith(".elf"):
            self.load_and_run_elf(filename)
        else:
            self.program_bitstream(filename)
