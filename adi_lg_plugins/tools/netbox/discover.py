"""Look on the exporter host for the hardware a board can be wired to; read-only.

`adi-lg netbox add-hardware` runs :data:`PROBE` there over SSH, so its
questions can default to what is plugged in:
- USB serial adapters, by their ``/dev/serial/by-id`` links;
- JTAG cables;
- USB SD muxes;
- Vivado installs.

Each is marked with the exporter config already using it.

The probe only lists directories and reads links, sysfs attributes and the
exporter configs. It never opens a device node, because opening a serial port
can reset a board. It runs nothing else. It prints only paths, IDs and file
names, because the configs hold passwords. It is sent as ``python3 -c``, since
the exporter host has Python for labgrid-exporter; that may be an older Python
than this package's, without PyYAML, so it uses the standard library only.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, replace

# argv[1] is prefixed to every path it reads: tests point it at a fake tree.
PROBE = r"""
import glob, json, os, re, sys

R = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else ""
DEV = r"/dev/[^\s'\"\],}]+"


def real(path):
    r = os.path.realpath(R + path)
    return r[len(R):] if R and r.startswith(R + "/") else r


def read(path):
    # sysfs attributes and exporter configs only: never a device node
    try:
        with open(R + path) as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def ls(path):
    try:
        return sorted(os.listdir(R + path))
    except OSError:
        return []


def up(path, attr):
    # the nearest sysfs directory at or above path that has attr
    d = real(path)
    while d.startswith("/sys/"):
        if os.path.exists(R + d + "/" + attr):
            return d
        d = os.path.dirname(d)
    return None


def usb(d):
    keys = ("idVendor", "idProduct", "manufacturer", "product", "serial")
    u = dict((k, read(d + "/" + k) if d else "") for k in keys)
    u["name"] = " ".join(v for v in (u["manufacturer"], u["product"]) if v)
    return u


# The exporter configs: those add-hardware deploys, and any a systemd unit runs.
configs = set(p[len(R):] for p in glob.glob(R + "/etc/labgrid/**/*.yaml", recursive=True))
units = glob.glob(R + "/etc/systemd/system/*.service")
units += glob.glob(R + "/home/*/.config/systemd/user/*.service")
for unit in units:
    unit = unit[len(R):]
    text = read(unit)
    if "labgrid-exporter" in text:
        if "/.config/systemd/user/" in unit:
            text = text.replace("%h", unit.split("/.config/")[0])
        configs.update(re.findall(r"/[^\s'\"]+\.ya?ml", text))

uses = {}  # each /dev path a config names, and what it resolves to -> the config
texts = {}  # each config, less its /dev paths -> for a udev match
jtag_users, sdmux_users = [], []
for c in sorted(configs):
    text = read(c)
    if "XilinxDeviceJTAG" in text:
        jtag_users.append(c)
    if "USBSDMuxDevice" in text:
        sdmux_users.append(c)
    for p in re.findall(DEV, text):
        uses.setdefault(p, c)
        uses.setdefault(real(p), c)
    texts[c] = re.sub(DEV, "", text)


def used_by(paths, serial, iface):
    # named by a /dev path, or matched by its serial number or its ID_PATH
    # (a USB interface 1-14.1:1.0 is ID_PATH ...-usb-0:14.1:1.0)
    for p in paths:
        if p in uses:
            return uses[p]
    port = "-usb-0:" + os.path.basename(iface).split("-", 1)[-1] if iface else None
    for c, text in texts.items():
        if (len(serial) >= 6 and serial in text) or (port and port in text):
            return c
    return ""


jtag, cables = [], set()
for n in ls("/sys/bus/usb/devices"):
    d = real("/sys/bus/usb/devices/" + n)
    if not os.path.exists(R + d + "/idVendor"):
        continue  # a USB interface, not a device
    u = usb(d)
    if (
        u["idVendor"] == "03fd"
        or "digilent" in u["manufacturer"].lower()
        or "jtag" in u["product"].lower()
    ):
        cables.add(d)
        usb_id = u["idVendor"] + ":" + u["idProduct"]
        jtag.append({"name": u["name"], "usb_id": usb_id, "serial": u["serial"]})

serial = []
for n in ls("/dev/serial/by-id"):
    link = "/dev/serial/by-id/" + n
    tty = real(link)
    sysfs = "/sys/class/tty/" + os.path.basename(tty) + "/device"
    d, iface = up(sysfs, "idVendor"), up(sysfs, "bInterfaceNumber")
    if d in cables and (not iface or read(iface + "/bInterfaceNumber") == "00"):
        continue  # a JTAG cable's JTAG channel
    u = usb(d)
    serial.append(
        {
            "link": link,
            "tty": tty,
            "adapter": u["name"],
            "serial": u["serial"],
            "used_by": used_by((link, tty), u["serial"], iface),
        }
    )

sdmuxes = []
for n in ls("/sys/class/scsi_generic"):
    scsi = real("/sys/class/scsi_generic/" + n + "/device")
    u = usb(up(scsi, "idVendor"))
    if (u["idVendor"], u["idProduct"]) != ("0424", "4041"):
        continue
    blocks = ls(scsi + "/block")
    disk = "/dev/" + blocks[0] if blocks else ""
    # a config may name the card's boot partition rather than the card
    parts = ["/dev/" + b for b in ls(scsi + "/block/" + blocks[0]) if b.startswith(blocks[0])] if blocks else []
    links = [
        "/dev/disk/by-id/" + name
        for name in ls("/dev/disk/by-id")
        if real("/dev/disk/by-id/" + name) == disk
    ]
    sdmuxes.append(
        {
            "serial": u["serial"],
            "sg": "/dev/" + n,
            "disk": links[0] if links else disk,
            "used_by": used_by(["/dev/" + n, disk] + parts, u["serial"], up(scsi, "bInterfaceNumber")),
        }
    )

vivado = []
for top in ("/tools/Xilinx", "/opt/Xilinx"):
    for edition in ("Vivado", "Vivado_Lab"):
        for p in glob.glob(R + top + "/*/" + edition) + glob.glob(R + top + "/" + edition + "/*"):
            p = p[len(R):]
            if re.search(r"/\d{4}\.\d", p):
                xsdb = os.path.exists(R + os.path.dirname(p) + "/Vitis/bin/xsdb")
                vivado.append({"path": p, "xsdb": xsdb})

found = {"serial": serial, "jtag": jtag, "sdmuxes": sdmuxes, "vivado": vivado}
found.update(jtag_users=jtag_users, sdmux_users=sdmux_users)
print(json.dumps(found))
"""


@dataclass(frozen=True)
class SerialAdapter:
    """A USB serial adapter, by the name udev gives it that doesn't change with plug order."""

    link: str  # its /dev/serial/by-id link
    tty: str  # the device the link points at now, e.g. /dev/ttyUSB0
    adapter: str  # USB manufacturer and product
    serial: str  # USB serial number
    used_by: str = ""  # the exporter config that names it; "" if none does


@dataclass(frozen=True)
class JTAGCable:
    name: str  # USB manufacturer and product
    usb_id: str  # vendor:product
    serial: str


@dataclass(frozen=True)
class SDMux:
    """A USB SD mux: the sg device that switches it, and the card reader it switches."""

    serial: str
    sg: str
    disk: str  # by its /dev/disk/by-id link if it has one
    used_by: str = ""

    @property
    def partition(self) -> str:
        """The card's first partition, its boot partition, named like the card."""
        return f"{self.disk}-part1" if "/by-id/" in self.disk else f"{self.disk}1"


@dataclass(frozen=True)
class VivadoInstall:
    path: str
    xsdb: bool  # the xsdb XilinxVivadoTool runs, in the Vitis beside it, is there


@dataclass(frozen=True)
class HostHardware:
    serial: tuple[SerialAdapter, ...] = ()
    jtag: tuple[JTAGCable, ...] = ()
    sdmuxes: tuple[SDMux, ...] = ()
    vivado: tuple[VivadoInstall, ...] = ()  # newest first
    jtag_users: tuple[str, ...] = ()  # the exporter configs that export a JTAG device
    sdmux_users: tuple[str, ...] = ()  # ... and those that export an SD mux

    @property
    def free_serial(self) -> tuple[SerialAdapter, ...]:
        return tuple(a for a in self.serial if not a.used_by)

    @property
    def free_sdmuxes(self) -> tuple[SDMux, ...]:
        """The muxes no config names, less one for each config that exports a mux it doesn't name."""
        named = {m.used_by for m in self.sdmuxes}
        unnamed = sum(c not in named for c in self.sdmux_users)
        return tuple(m for m in self.sdmuxes if not m.used_by)[unnamed:]

    @property
    def free_jtag(self) -> bool:
        """Whether there are more JTAG cables than exporter configs using one.

        A config doesn't say which cable it uses (xsdb finds the device by its
        target), so they are counted.
        """
        return len(self.jtag) > len(self.jtag_users)

    @property
    def vivado_path(self) -> str | None:
        """The newest Vivado install a template's ``vivado_path`` can name as it is."""
        return next((v.path for v in self.vivado if v.xsdb), None)

    def without(self, config: str) -> HostHardware:
        """What was found, with ``config`` (the board's own exporter config) using none of it."""

        def free(items):
            return tuple(replace(i, used_by="") if i.used_by == config else i for i in items)

        return replace(
            self,
            serial=free(self.serial),
            sdmuxes=free(self.sdmuxes),
            jtag_users=tuple(c for c in self.jtag_users if c != config),
            sdmux_users=tuple(c for c in self.sdmux_users if c != config),
        )


def _newest_first(install: VivadoInstall):
    version = re.search(r"/(\d{4})\.(\d+)", install.path)
    return (-int(version[1]), -int(version[2])) if version else (0, 0), install.path


def parse(output: str) -> HostHardware:
    """The probe's JSON report, as :class:`HostHardware`."""
    try:
        found = json.loads(output)
        return HostHardware(
            serial=tuple(SerialAdapter(**a) for a in found["serial"]),
            jtag=tuple(JTAGCable(**c) for c in found["jtag"]),
            sdmuxes=tuple(SDMux(**m) for m in found["sdmuxes"]),
            vivado=tuple(sorted((VivadoInstall(**v) for v in found["vivado"]), key=_newest_first)),
            jtag_users=tuple(found["jtag_users"]),
            sdmux_users=tuple(found["sdmux_users"]),
        )
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f"unexpected output from the probe: {output[:200]!r}") from e


def discover_host(ssh_host: str, *, root: str = "") -> HostHardware:
    """What :data:`PROBE` finds on ``ssh_host``.

    Raises RuntimeError, with the reason, if it can't look there: SSH fails,
    the host has no ``python3``, or the probe fails. ``root`` is prefixed to
    every path the probe reads.
    """
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    command = f"python3 -c {shlex.quote(PROBE)}" + (f" {shlex.quote(root)}" if root else "")
    try:
        stdout, stderr, status = sshmanager.get(ssh_host).run(command)
    except ExecutionError as e:
        # labgrid's message lists every ssh argument before ssh's own reason.
        reason = re.search(r"ssh: [^\\'\r\n]+", e.msg)
        raise RuntimeError(reason[0] if reason else e.msg) from e
    if status != 0:
        raise RuntimeError(stderr[-1] if stderr else f"the probe exited with status {status}")
    # A login script may print a banner first; the report is the last line.
    return parse(stdout[-1] if stdout else "")
