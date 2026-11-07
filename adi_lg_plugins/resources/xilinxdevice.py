"""Xilinx FPGA device JTAG configuration resource."""

import re

import attr
from labgrid.factory import target_factory
from labgrid.resource import Resource

# JTAG cable serials (Digilent, Xilinx Platform Cable, FTDI) are alphanumeric;
# they end up inside an xsdb Tcl filter, so nothing else is accepted.
_SERIAL = re.compile(r"[A-Za-z0-9_-]+")
# hw_server agent URL as xsdb's `connect -url` takes it: tcp:<host>:<port>, where an
# empty host (tcp::3121) means the place's exporter host.
_AGENT_URL = re.compile(r"(?i)tcp:[A-Za-z0-9.\-]*:[0-9]{1,5}")


def _optional_match(pattern, what):
    def validate(_instance, attribute, value):
        if value is None:
            return
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ValueError(f"{attribute.name} must be {what}, got {value!r}")

    return validate


@target_factory.reg_resource
@attr.s(eq=False)
class XilinxDeviceJTAG(Resource):
    """Xilinx FPGA device JTAG configuration.

    Defines JTAG target IDs and file paths for Virtex/Artix/Kintex FPGAs
    with Microblaze soft processors.

    Attributes:
        root_target (int): JTAG target ID for root device (default: 1).
            This is typically the FPGA fabric target identified by xsdb 'targets' command.
        microblaze_target (int): JTAG target ID for Microblaze processor (default: 3).
            This is typically the processor core target for xsdb commands.
        bitstream_path (str, optional): Path to FPGA bitstream file (.bit).
            Required when using BootFabric strategy. Caller-local files are
            staged to the exporter automatically. Prefix with ``exporter:``
            for a file which already exists on the exporter.
        kernel_path (str, optional): Path to Microblaze Linux kernel image (.strip).
            Required when using BootFabric strategy. Uses the same staging and
            ``exporter:`` compatibility semantics as ``bitstream_path``.
        devicetree_path (str, optional): Path to device tree binary (.dtb).
            Only needed if device tree is separate from kernel image.
        serial (str, optional): JTAG cable serial (e.g. ``210308A474DF``). Every
            target xsdb selects is then restricted to that cable, so a host with
            several cables drives the right board; with a wrong serial xsdb finds
            no target and the call fails.
        agent_url (str, optional): hw_server to connect to, as
            ``tcp:<host>:<port>``. ``tcp::3121`` (empty host) means the place's
            exporter host. When set, xsdb runs on the client and connects to that
            hw_server over TCP instead of running on the exporter over ssh.
    """

    name = attr.ib(default="xilinxdevicejtag")

    # JTAG target IDs (from xsdb 'targets' command output)
    root_target = attr.ib(
        default=1,
        validator=attr.validators.instance_of(int),
    )
    microblaze_target = attr.ib(
        default=3,
        validator=attr.validators.instance_of(int),
    )

    # File paths
    bitstream_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    kernel_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    # Optional device tree (if not embedded in kernel)
    devicetree_path = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )

    # Optional cable selection / hw_server endpoint
    serial = attr.ib(
        default=None,
        validator=_optional_match(_SERIAL, "a JTAG cable serial ([A-Za-z0-9_-])"),
    )
    agent_url = attr.ib(
        default=None,
        validator=_optional_match(_AGENT_URL, "tcp:<host>:<port> (host may be empty)"),
    )
