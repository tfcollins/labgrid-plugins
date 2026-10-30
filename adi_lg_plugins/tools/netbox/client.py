"""NetBox inventory client: idempotent schema setup + device upsert.

Targets the NetBox v4.7 API (the version pinned in cse-openshift-apps'
``charts/netbox/values.yaml``) via ``pynetbox``. NetBox 4.3 renamed custom
fields' ``content_types`` to ``object_types`` - this module uses the newer
name; bump it back if pointed at an older NetBox.

Schema auto-provisioning is scoped deliberately: this module creates/owns
the ``labgrid-target`` device role, its custom fields, and board device
types/manufacturer (all labgrid-specific) - but never creates a Site. Sites
are physical-location truth the organization manages deliberately; this
tool only looks one up by slug and fails clearly if it doesn't exist.

A board's power is recorded the standard NetBox way: a cable from a power
port on the board to a power outlet on the device that switches it (PDU,
smart plug, relay, ...). Power devices already in NetBox are used as they
are; one that is missing is created under the ``labgrid-power`` role. Its
``labgrid_power`` custom field holds the labgrid power type and the settings
that identify it, so the next board on it is configured from NetBox.

Its serial console and JTAG go the same way: a cable from a console port on
the board (``UART``, ``JTAG``) to a console server port on the device the
adapter is plugged into - usually the exporter host, created under the
``labgrid-console-server`` role if NetBox doesn't have it. A serial port's
``labgrid_serial_path`` custom field holds its device path on the exporter
host (a port name is limited to 64 characters; ``/dev/serial/by-id`` paths
are often longer). NetBox has no JTAG component, so JTAG uses console ports
too - a record of the wiring only; labgrid's JTAG settings don't depend on it.

The SD card a board boots from can sit in a USB SD mux. NetBox has no SD card
component either, so that is a cable from an ``SD`` interface on the board to
the ``DUT`` interface of the mux, a device with the ``labgrid-sd-mux`` role
(created if missing) and its USB serial number in NetBox's ``serial`` field.
Its ``labgrid_sdmux`` custom field holds its control device and the card's
boot partition on the exporter host, so the next board in it is configured
from NetBox.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass

import requests
import urllib3

from adi_lg_plugins.hw_ci.power import POWER_TYPES, PowerType

logger = logging.getLogger(__name__)

DEVICE_ROLE_SLUG = "labgrid-target"
DEVICE_ROLE_NAME = "Labgrid Target"
MANUFACTURER_SLUG = "adi-lab"
MANUFACTURER_NAME = "Analog Devices, Inc. (lab hardware)"

# Power devices and console servers this tool creates are third-party
# hardware, not ADI's.
POWER_ROLE_SLUG = "labgrid-power"
POWER_ROLE_NAME = "Labgrid Power Control"
POWER_MANUFACTURER_SLUG = "generic"
POWER_MANUFACTURER_NAME = "Generic"
POWER_FIELD = "labgrid_power"
CONSOLE_ROLE_SLUG = "labgrid-console-server"
CONSOLE_ROLE_NAME = "Labgrid Console Server"
SERIAL_PATH_FIELD = "labgrid_serial_path"
# The board's console port for each kind of console connection.
UART = "UART"
JTAG = "JTAG"
SDMUX_ROLE_SLUG = "labgrid-sd-mux"
SDMUX_ROLE_NAME = "Labgrid SD Mux"
SDMUX_FIELD = "labgrid_sdmux"
# The interfaces an SD mux cable joins: the board's card slot, the mux's card side.
SD = "SD"
SDMUX_PORT = "DUT"
# The outlet of a single switch (smart plug, relay, ...), and of a strip used whole.
SINGLE_OUTLET = "1"
# A board's power ports, when it has none to reuse: "power", "power 2", ...
POWER_PORT = "power"

# custom field name -> (label, NetBox field type, object type it is on)
CUSTOM_FIELDS: dict[str, tuple[str, str, str]] = {
    "carrier": ("Carrier", "text", "dcim.device"),
    "daughter_board": ("Daughter board / chip", "text", "dcim.device"),
    "boot_strategy": ("Boot strategy", "text", "dcim.device"),
    "exporter_host": ("Exporter SSH target", "text", "dcim.device"),
    "runner_label": ("GitHub runner label", "text", "dcim.device"),
    POWER_FIELD: ("Labgrid power control", "json", "dcim.device"),
    SERIAL_PATH_FIELD: ("Labgrid serial device path", "text", "dcim.consoleserverport"),
    SDMUX_FIELD: ("Labgrid SD mux", "json", "dcim.device"),
}


def _require_pynetbox():
    try:
        import pynetbox
    except ImportError as e:
        raise RuntimeError(
            "pynetbox is required for `adi-lg netbox` commands; "
            'run `pip install -e ".[netbox]"` in your labgrid-plugins checkout'
        ) from e
    return pynetbox


class _Session(requests.Session):
    """A session whose ``verify=False`` or CA-bundle path isn't overridden by the environment.

    requests otherwise swaps in ``REQUESTS_CA_BUNDLE`` / ``CURL_CA_BUNDLE`` for every request
    pynetbox makes, since pynetbox never passes ``verify`` itself.
    """

    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        settings = super().merge_environment_settings(url, proxies, stream, verify, cert)
        if self.verify is not True:
            settings["verify"] = self.verify
        return settings


# NetBox 4.5+ (authentication.py) accepts exactly "Bearer nbt_<key>.<token>"
# or "Token <token>"; pynetbox adds the keyword, so it must not be in the token.
_TOKEN_FORMAT = "nbt_<key>.<token> (NetBox 4.5+) or the 40-character v1 token"
_HEADER_PREFIX = re.compile(r"^(?:authorization:\s*)?(?:bearer|token)(?:\s+|$)", re.IGNORECASE)


def clean_token(raw: str) -> str:
    """The bare API token from what was pasted or set, or ValueError saying what's wrong.

    Drops surrounding whitespace and quotes and a pasted ``Authorization:``
    ``Bearer``/``Token`` prefix. Rejects what NetBox can't parse: spaces inside
    the token, or only the key half of a v2 token.
    """
    token = _HEADER_PREFIX.sub("", raw.strip().strip("\"'").strip())
    if not token:
        raise ValueError(f"the token is empty - expected {_TOKEN_FORMAT}")
    if any(c.isspace() for c in token):
        raise ValueError(f"the token contains a space - paste only the token: {_TOKEN_FORMAT}")
    if token.startswith("nbt_") and "." not in token:
        raise ValueError(
            "that is only the key of a v2 token - the full token is nbt_<key>.<token>, "
            "shown once when the token is created"
        )
    return token


def connect(url: str, token: str, *, verify: bool | str = True):
    """Return a connected ``pynetbox.api`` instance.

    ``verify`` is requests' TLS setting: ``False`` skips certificate checks, a
    path names a CA bundle (for a NetBox behind an internal CA).
    """
    pynetbox = _require_pynetbox()
    nb = pynetbox.api(url, token=token)
    nb.http_session = _Session()
    nb.http_session.verify = verify
    if verify is False:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return nb


@contextmanager
def reported_errors(url: str):
    """Re-raise TLS, connection, and API failures as RuntimeError with a hint."""
    pynetbox = _require_pynetbox()
    try:
        yield
    except requests.exceptions.SSLError as e:
        raise RuntimeError(
            f"TLS verification failed for {url}: {e}\n"
            "If NetBox uses an internal CA, pass --netbox-ca-bundle <ca.pem> (on Debian/Ubuntu "
            "the system trust store is /etc/ssl/certs/ca-certificates.crt), or drop "
            "--netbox-verify / --netbox-ca-bundle to skip verification"
        ) from e
    except OSError as e:  # RequestException, or a CA bundle path that doesn't exist
        raise RuntimeError(f"could not reach NetBox at {url}: {e}") from e
    except pynetbox.RequestError as e:
        hint = ""
        if e.req.status_code in (401, 403):
            hint = " - check the API token (--netbox-token / NETBOX_TOKEN)"
        if "Invalid authorization header" in str(e):
            hint = (
                f" - give the bare token, without the Bearer/Token keyword: {_TOKEN_FORMAT} "
                "(--netbox-token / NETBOX_TOKEN)"
            )
        raise RuntimeError(f"NetBox rejected the request: {e}{hint}") from e


def ensure_schema(nb) -> None:
    """Idempotently ensure the labgrid-target role + custom fields exist.

    Safe to call on every run - each object is only created if missing.
    """
    role = nb.dcim.device_roles.get(slug=DEVICE_ROLE_SLUG)
    if role is None:
        logger.info("creating NetBox device role %r", DEVICE_ROLE_SLUG)
        nb.dcim.device_roles.create(name=DEVICE_ROLE_NAME, slug=DEVICE_ROLE_SLUG, color="2196f3")

    mfr = nb.dcim.manufacturers.get(slug=MANUFACTURER_SLUG)
    if mfr is None:
        logger.info("creating NetBox manufacturer %r", MANUFACTURER_SLUG)
        nb.dcim.manufacturers.create(name=MANUFACTURER_NAME, slug=MANUFACTURER_SLUG)

    for name, (label, cf_type, object_type) in CUSTOM_FIELDS.items():
        if nb.extras.custom_fields.get(name=name) is None:
            logger.info("creating NetBox custom field %r", name)
            nb.extras.custom_fields.create(
                object_types=[object_type],
                type=cf_type,
                name=name,
                label=label,
            )


def ensure_device_type(nb, carrier: str) -> int:
    """Idempotently ensure a Device Type exists for `carrier`; return its id."""
    slug = carrier.lower().replace("_", "-")
    dt = nb.dcim.device_types.get(slug=slug)
    if dt is not None:
        return dt.id
    mfr = nb.dcim.manufacturers.get(slug=MANUFACTURER_SLUG)
    if mfr is None:
        raise RuntimeError("NetBox manufacturer missing - call ensure_schema() first")
    logger.info("creating NetBox device type %r", carrier)
    dt = nb.dcim.device_types.create(manufacturer=mfr.id, model=carrier.upper(), slug=slug)
    return dt.id


def create_or_update_device(nb, name: str, *, carrier: str, site_slug: str, custom_fields: dict):
    """Create the device if missing, else update its custom fields in place."""
    site = nb.dcim.sites.get(slug=site_slug)
    if site is None:
        raise RuntimeError(
            f"NetBox site {site_slug!r} does not exist - this tool only references "
            "existing sites, it does not create them"
        )
    device_type_id = ensure_device_type(nb, carrier)
    role = nb.dcim.device_roles.get(slug=DEVICE_ROLE_SLUG)

    device = nb.dcim.devices.get(name=name)
    if device is None:
        logger.info("creating NetBox device %r", name)
        device = nb.dcim.devices.create(
            name=name,
            device_type=device_type_id,
            role=role.id,
            site=site.id,
            custom_fields=custom_fields,
        )
    else:
        logger.info("updating NetBox device %r", name)
        device.custom_fields.update(custom_fields)
        device.save()
    return device


# --- Power: board power port -> cable -> outlet on a power device -----------


@dataclass(frozen=True)
class PowerOutlet:
    name: str
    connected_to: str | None = None  # "<device> <port>" its cable feeds, None if free


@dataclass(frozen=True)
class PowerDevice:
    name: str
    settings: dict  # its labgrid_power custom field; {} on a device made by hand
    address: str = ""  # primary IP, without the prefix length
    outlets: tuple[PowerOutlet, ...] = ()


def _peers(termination) -> list[str]:
    return [f"{p.device.name} {p.name}" for p in termination.link_peers or ()]


def sites(nb) -> list[tuple[str, str]]:
    """Every site's slug and name."""
    return sorted((s.slug, s.name) for s in nb.dcim.sites.all())


def _devices_with(nb, endpoint: str, site_slug: str):
    """``(device, its ports, its address)`` for each device at a site with ``endpoint`` ports."""
    ports: dict[int, list] = {}
    for port in getattr(nb.dcim, endpoint).filter(site=site_slug):
        ports.setdefault(port.device.id, []).append(port)
    if not ports:
        return []
    found = []
    for device in nb.dcim.devices.filter(id=list(ports)):
        ip = getattr(device, "primary_ip", None)
        address = ip.address.split("/")[0] if ip else ""
        found.append((device, sorted(ports[device.id], key=lambda p: _natural(p.name)), address))
    return sorted(found, key=lambda d: d[0].name)


def power_devices(nb, site_slug: str) -> list[PowerDevice]:
    """The devices at a site that have power outlets, with what each outlet feeds."""
    found = []
    for device, outlets, address in _devices_with(nb, "power_outlets", site_slug):
        settings = (device.custom_fields or {}).get(POWER_FIELD)
        found.append(
            PowerDevice(
                device.name,
                settings if isinstance(settings, dict) else {},
                address,
                tuple(PowerOutlet(o.name, ", ".join(_peers(o)) or None) for o in outlets),
            )
        )
    return found


@dataclass(frozen=True)
class ConsoleServerPort:
    name: str
    path: str = ""  # its labgrid_serial_path: the serial device on the exporter host
    connected_to: str | None = None  # "<device> <port>" its cable feeds, None if free
    jtag: bool = False  # it feeds a board's JTAG port


@dataclass(frozen=True)
class ConsoleDevice:
    name: str
    address: str = ""  # primary IP, without the prefix length
    ports: tuple[ConsoleServerPort, ...] = ()


def console_devices(nb, site_slug: str) -> list[ConsoleDevice]:
    """The devices at a site with console server ports, with each port's path and what it feeds."""
    return [
        ConsoleDevice(
            device.name,
            address,
            tuple(
                ConsoleServerPort(
                    p.name,
                    (p.custom_fields or {}).get(SERIAL_PATH_FIELD) or "",
                    ", ".join(_peers(p)) or None,
                    any(_is_kind(JTAG, peer.name) for peer in p.link_peers or ()),
                )
                for p in ports
            ),
        )
        for device, ports, address in _devices_with(nb, "console_server_ports", site_slug)
    ]


@dataclass(frozen=True)
class SDMux:
    name: str
    serial: str  # its USB serial number; "" if NetBox hasn't one
    settings: dict  # its labgrid_sdmux custom field; {} on a mux made by hand
    connected_to: str | None = None  # "<device> <port>" its DUT side feeds, None if free


def sd_muxes(nb, site_slug: str) -> list[SDMux]:
    """The devices at a site with the SD mux role, with each one's settings and what it feeds."""
    role = nb.dcim.device_roles.get(slug=SDMUX_ROLE_SLUG)
    if role is None:
        return []
    found = []
    for device in nb.dcim.devices.filter(site=site_slug, role_id=role.id):
        dut = nb.dcim.interfaces.filter(device_id=device.id, name=SDMUX_PORT)
        settings = (device.custom_fields or {}).get(SDMUX_FIELD)
        found.append(
            SDMux(
                device.name,
                device.serial or "",
                settings if isinstance(settings, dict) else {},
                ", ".join(peer for i in dut for peer in _peers(i)) or None,
            )
        )
    return sorted(found, key=lambda m: m.name)


def device_exists(nb, name: str, site_slug: str) -> bool:
    return bool(list(nb.dcim.devices.filter(name=name, site=site_slug)))


def outlet_label(device: str, outlet: str) -> str:
    """e.g. "pdu3 outlet 4", but "pdu3 Outlet 4" for an outlet named that way."""
    return f"{device} outlet {outlet}" if outlet.isdigit() else f"{device} {outlet}"


def _natural(name: str):
    """Sort key putting outlet "2" before "10"."""
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", name)]


def _get_or_create(endpoint, slug: str, **fields):
    """By slug, else by its unique name (one made by hand may have another slug), else created."""
    found = endpoint.get(slug=slug)
    if found is None:
        unique = (
            {"model": fields["model"], "manufacturer_id": fields["manufacturer"]}
            if "model" in fields
            else {"name": fields["name"]}
        )
        found = next(iter(endpoint.filter(**unique)), None)
    return found or endpoint.create(slug=slug, **fields)


def _create_device(
    nb, name: str, site_id: int, *, role, type_slug, model, custom_fields=None, serial=""
):
    role = _get_or_create(nb.dcim.device_roles, role[0], name=role[1], color=role[2])
    mfr = _get_or_create(
        nb.dcim.manufacturers, POWER_MANUFACTURER_SLUG, name=POWER_MANUFACTURER_NAME
    )
    device_type = _get_or_create(nb.dcim.device_types, type_slug, manufacturer=mfr.id, model=model)
    logger.info("creating NetBox device %r", name)
    return nb.dcim.devices.create(
        name=name,
        device_type=device_type.id,
        role=role.id,
        site=site_id,
        serial=serial,
        custom_fields=custom_fields or {},
    )


@dataclass(frozen=True)
class _Ends:
    """One kind of cabled connection: board-side ports and the far-side ports they plug into."""

    board: str  # board-side endpoint, e.g. "power_ports"
    board_type: str  # its cable termination type
    far: str  # far-side endpoint, e.g. "power_outlets"
    far_type: str
    port: str  # name of a board port added for it: "power", "power 2", ...
    reuse: tuple[str, ...] = ()  # board ports of this kind start so (lowercase); () = any
    port_fields: tuple[tuple[str, object], ...] = ()  # set on a board port added for it


_POWER = _Ends("power_ports", "dcim.powerport", "power_outlets", "dcim.poweroutlet", POWER_PORT)
_CONSOLE = {
    # The templates' RawSerialPort runs at 115200 baud.
    UART: _Ends(
        "console_ports",
        "dcim.consoleport",
        "console_server_ports",
        "dcim.consoleserverport",
        UART,
        ("uart", "console", "serial"),
        (("speed", 115200),),
    ),
    JTAG: _Ends(
        "console_ports",
        "dcim.consoleport",
        "console_server_ports",
        "dcim.consoleserverport",
        JTAG,
        ("jtag",),
    ),
}
_SDMUX = _Ends(
    "interfaces",
    "dcim.interface",
    "interfaces",
    "dcim.interface",
    SD,
    ("sd",),
    (("type", "other"),),
)


def _is_kind(kind: str, port_name: str) -> bool:
    return port_name.lower().startswith(_CONSOLE[kind].reuse)


def _port_label(device: str, port: str) -> str:
    return f"{device} {port}"


def _connect(
    nb, board, ends: _Ends, *, site_slug, device, names, label, create, settle, far_fields=None
) -> list[str]:
    """Cable ``board`` to the far-side ports ``names`` on ``device`` at the board's site.

    ``create(site_id)`` makes ``device`` if the site has no device of that
    name; ``settle(device, ports)`` brings an existing one up to date and
    returns what it did. Missing far-side ports are created with
    ``far_fields``. The board's free ports of this kind are used before new
    ones are added. Cables already there stay: a port feeding another device
    is refused before anything is written, and the board's other connections
    of this kind are reported, not removed. Returns what was done, one line each.
    """
    site = nb.dcim.sites.get(slug=site_slug)
    if site is None:
        raise RuntimeError(f"NetBox site {site_slug!r} does not exist")
    found = list(nb.dcim.devices.filter(name=device, site_id=site.id))
    far_device = found[0] if found else None
    existing = {}
    if far_device is not None:
        existing = {o.name: o for o in getattr(nb.dcim, ends.far).filter(device_id=far_device.id)}
    all_ports = sorted(
        getattr(nb.dcim, ends.board).filter(device_id=board.id), key=lambda p: _natural(p.name)
    )
    ports = [p for p in all_ports if not ends.reuse or p.name.lower().startswith(ends.reuse)]
    mine = {f"{board.name} {p.name}" for p in ports}
    for name in names:
        others = [p for p in _peers(existing[name]) if p not in mine] if name in existing else []
        if others:
            raise RuntimeError(
                f"{label(device, name)} already feeds {', '.join(others)} - pick a free "
                "one, or remove that cable in NetBox first"
            )

    done = []
    if far_device is None:
        far_device = create(site.id)
    else:
        done += settle(far_device, existing)

    used = {p.id for p in ports if p.cable is not None}
    wanted = {f"{device} {name}" for name in names}
    for name in names:
        far = existing.get(name)
        if far is None:
            far = getattr(nb.dcim, ends.far).create(
                device=far_device.id, name=name, **(far_fields or {})
            )
        elif _peers(far):
            done.append(f"{board.name} is already connected to {label(device, name)}")
            continue
        port = next((p for p in ports if p.id not in used), None)
        if port is None:
            taken = {p.name for p in all_ports}
            port_name = next(
                n
                for n in (ends.port, *(f"{ends.port} {i}" for i in range(2, len(all_ports) + 3)))
                if n not in taken
            )
            port = getattr(nb.dcim, ends.board).create(
                device=board.id, name=port_name, **dict(ends.port_fields)
            )
            ports.append(port)
            all_ports.append(port)
        used.add(port.id)
        nb.dcim.cables.create(
            a_terminations=[{"object_type": ends.board_type, "object_id": port.id}],
            b_terminations=[{"object_type": ends.far_type, "object_id": far.id}],
        )
        done.append(f"connected {board.name} {port.name} to {label(device, name)}")
    for port in ports:
        for peer in _peers(port):
            if peer not in wanted:
                done.append(
                    f"{board.name} {port.name} is also connected to {peer} - left as is; "
                    "remove that cable in NetBox if the board was moved"
                )
    return done


def connect_power(
    nb, board, *, site_slug: str, device: str, settings: dict, outlets: list[str]
) -> list[str]:
    """Cable ``board``'s power to ``outlets`` on power device ``device`` at the board's site.

    The device and its outlets are created if missing; ``settings`` (the
    ``labgrid_power`` value) fill in a device's empty field but never replace
    one. See :func:`_connect` for how cables are added.
    """
    done = []

    def create(site_id):
        done.append(f"created power device {device}")
        return _create_device(
            nb,
            device,
            site_id,
            role=(POWER_ROLE_SLUG, POWER_ROLE_NAME, "ff9800"),
            type_slug=f"labgrid-power-{settings['type']}",
            model=POWER_TYPES[settings["type"]].label,
            custom_fields={POWER_FIELD: settings},
        )

    return done + _connect(
        nb,
        board,
        _POWER,
        site_slug=site_slug,
        device=device,
        names=outlets,
        label=outlet_label,
        create=create,
        settle=lambda power_device, outlets: _settle(
            power_device, POWER_FIELD, settings, "labgrid power settings"
        ),
    )


def _settle(device, field: str, settings: dict, what: str) -> list[str]:
    """Fill in ``device``'s empty ``field`` with ``settings``; one already set is kept."""
    current = (device.custom_fields or {}).get(field)
    if not current:
        device.custom_fields[field] = settings
        device.save()
        return [f"recorded the {what} on {device.name}"]
    if current != settings:
        return [
            f"{device.name} keeps its {field} settings in NetBox ({current}), "
            f"which differ from this board's ({settings})"
        ]
    return []


def connect_console(
    nb, board, *, kind: str, site_slug: str, device: str, port: str, path: str = ""
) -> list[str]:
    """Cable ``board``'s ``kind`` (UART or JTAG) console port to ``port`` on ``device``.

    ``device`` (usually the exporter host) gets the console server port if it
    hasn't one of that name, and is created under the console server role if
    the site has no device of that name. ``path`` is the serial device on the
    exporter host: it fills in the port's empty ``labgrid_serial_path`` but
    never replaces one. See :func:`_connect` for how cables are added.
    """
    done = []

    def create(site_id):
        done.append(f"created console server {device}")
        return _create_device(
            nb,
            device,
            site_id,
            role=(CONSOLE_ROLE_SLUG, CONSOLE_ROLE_NAME, "607d8b"),
            type_slug=CONSOLE_ROLE_SLUG,
            model="Console server (USB serial / JTAG adapters)",
        )

    def settle(host, ports):
        if not path or port not in ports:
            return []
        current = (ports[port].custom_fields or {}).get(SERIAL_PATH_FIELD)
        if not current:
            ports[port].custom_fields[SERIAL_PATH_FIELD] = path
            ports[port].save()
            return [f"recorded the serial path {path} on {device} {port}"]
        if current != path:
            return [
                f"{device} {port} keeps its serial path in NetBox ({current}), "
                f"which differs from this board's ({path})"
            ]
        return []

    return done + _connect(
        nb,
        board,
        _CONSOLE[kind],
        site_slug=site_slug,
        device=device,
        names=[port],
        label=_port_label,
        create=create,
        settle=settle,
        far_fields={"custom_fields": {SERIAL_PATH_FIELD: path}} if path else None,
    )


def connect_sdmux(
    nb, board, *, site_slug: str, device: str, serial: str, settings: dict
) -> list[str]:
    """Cable ``board``'s SD card slot to SD mux ``device`` at the board's site.

    The mux, and its ``DUT`` interface, are created if missing. ``settings``
    (the ``labgrid_sdmux`` value) and ``serial`` fill in the mux's empty field
    and serial number but never replace them. See :func:`_connect` for how
    cables are added.
    """
    done = []

    def create(site_id):
        done.append(f"created SD mux {device}")
        return _create_device(
            nb,
            device,
            site_id,
            role=(SDMUX_ROLE_SLUG, SDMUX_ROLE_NAME, "8bc34a"),
            type_slug=SDMUX_ROLE_SLUG,
            model="USB SD mux",
            custom_fields={SDMUX_FIELD: settings},
            serial=serial,
        )

    def settle(mux, interfaces):
        if serial and not mux.serial:
            mux.serial = serial
            mux.save()
            done.append(f"recorded the serial number {serial} on {device}")
        return _settle(mux, SDMUX_FIELD, settings, "SD mux settings")

    return done + _connect(
        nb,
        board,
        _SDMUX,
        site_slug=site_slug,
        device=device,
        names=[SDMUX_PORT],
        label=_port_label,
        create=create,
        settle=settle,
        far_fields={"type": "other"},
    )


def power_settings(power: PowerType, context: dict) -> dict:
    """The ``labgrid_power`` value for a power device: its type and identifying fields."""
    return {
        "type": power.key,
        **{f.param: context[f.var] for f in power.device_fields if f.var in context},
    }


def power_answers(settings) -> tuple[str, dict[str, str]] | None:
    """The power type and device-field answers in a ``labgrid_power`` value.

    None unless it names a known type and has that type's required fields.
    """
    power = POWER_TYPES.get(settings.get("type")) if isinstance(settings, dict) else None
    if power is None:
        return None
    answers = {f.var: str(settings[f.param]) for f in power.device_fields if f.param in settings}
    if any(f.default is None and f.var not in answers for f in power.device_fields):
        return None
    return power.key, answers


def outlet_names(power: PowerType, value) -> list[str]:
    """The NetBox outlet(s) an outlet answer names; a comma list names several."""
    names = [v.strip() for v in str(value or "").split(",") if v.strip()]
    return names if power.outlet_field and names else [SINGLE_OUTLET]


def outlet_answer(power: PowerType, outlet: str, outlets: int) -> str | None:
    """The outlet field's answer for NetBox outlet ``outlet`` (of ``outlets`` on its device).

    None when the name doesn't give it (e.g. "Outlet 4" for a number), so it is asked.
    """
    field = power.outlet_field
    if field is None:
        return None
    if field.kind == "int":
        return outlet if outlet.isdigit() else None
    if field.default == "" and outlets == 1:
        return ""
    return outlet
