"""Xilinx USB JTAG adapter resource definitions.

Compatible with upstream labgrid PR #706 (XilinxUSBJTAG / NetworkXilinxUSBJTAG).
"""

from __future__ import annotations

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource

try:
    from labgrid.resource.udev import USBResource
except ImportError:
    USBResource = Resource

try:
    from labgrid.resource.remote import ManagedResource, NetworkResource
except ImportError:
    NetworkResource = Resource
    ManagedResource = Resource


@target_factory.reg_resource
@attr.s(eq=False)
class XilinxUSBJTAG(USBResource):
    """Xilinx-compatible USB JTAG adapter resource.

    Compatible with upstream labgrid PR #706. Matches USB devices such as:
    - Digilent JTAG-HS3 / JTAG-SMT2 (0403:6014)
    - Trenz TE0790-03 (0403:6010)
    - Xilinx Platform Cable USB (03fd:0013)
    - Xilinx Platform Cable USB II (03fd:0008)

    Attributes:
        hw_server_cmd: Command to launch hw_server (default: 'hw_server').
        serial: Optional cable serial number or port filter.
        agent_url: Agent listening URL (e.g. 'tcp::3121' or 'tcp:<host>:<port>').
        gdb_port: Base port number for GDB server (0 or int).
        log_level: List of log category strings for hw_server.
        extra_args: Additional command line arguments passed to hw_server.
    """

    hw_server_cmd = attr.ib(default="hw_server", validator=attr.validators.instance_of(str))
    serial = attr.ib(default="", validator=attr.validators.instance_of(str))
    agent_url = attr.ib(default="", validator=attr.validators.instance_of(str))
    gdb_port = attr.ib(default=0, validator=attr.validators.instance_of(int))
    log_level = attr.ib(factory=list, validator=attr.validators.instance_of(list))
    extra_args = attr.ib(factory=list, validator=attr.validators.instance_of(list))

    def __attrs_post_init__(self):
        if hasattr(self, "match") and isinstance(self.match, dict):
            self.match["DEVTYPE"] = "usb_device"
        super().__attrs_post_init__()

    def filter_match(self, device):
        match = (device.properties.get("ID_VENDOR_ID"), device.properties.get("ID_MODEL_ID"))
        supported = [
            ("0403", "6010"),  # Trenz Electronic TE0790-03
            ("0403", "6014"),  # Digilent JTAG-SMT2/JTAG-HS3
            ("03fd", "0013"),  # Xilinx Platform Cable USB
            ("03fd", "0008"),  # Xilinx Platform Cable USB II
        ]
        if match not in supported and match != (None, None):
            return False
        if hasattr(super(), "filter_match"):
            return super().filter_match(device)
        return True


@target_factory.reg_resource
@attr.s(eq=False)
class NetworkXilinxUSBJTAG(NetworkResource, ManagedResource):
    """Network-exported Xilinx USB JTAG adapter resource.

    Published by an exporter running VivadoHWServerExport (or proxying a XilinxUSBJTAG adapter).
    """

    hw_server_cmd = attr.ib(default="hw_server", validator=attr.validators.instance_of(str))
    serial = attr.ib(default="", validator=attr.validators.instance_of(str))
    agent_url = attr.ib(default="", validator=attr.validators.instance_of(str))
    gdb_port = attr.ib(default=0, validator=attr.validators.instance_of(int))
    log_level = attr.ib(factory=list, validator=attr.validators.instance_of(list))
    extra_args = attr.ib(factory=list, validator=attr.validators.instance_of(list))

    def __attrs_post_init__(self):
        self.timeout = 10.0
        super().__attrs_post_init__()
