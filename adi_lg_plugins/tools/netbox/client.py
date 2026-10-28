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

# Power devices this tool creates are third-party hardware, not ADI's.
POWER_ROLE_SLUG = "labgrid-power"
POWER_ROLE_NAME = "Labgrid Power Control"
POWER_MANUFACTURER_SLUG = "generic"
POWER_MANUFACTURER_NAME = "Generic"
POWER_FIELD = "labgrid_power"
# The outlet of a single switch (smart plug, relay, ...), and of a strip used whole.
SINGLE_OUTLET = "1"
# A board's power ports, when it has none to reuse: "power", "power 2", ...
POWER_PORT = "power"

# custom field name -> (label, NetBox field type)
CUSTOM_FIELDS: dict[str, tuple[str, str]] = {
    "carrier": ("Carrier", "text"),
    "daughter_board": ("Daughter board / chip", "text"),
    "boot_strategy": ("Boot strategy", "text"),
    "exporter_host": ("Exporter SSH target", "text"),
    "runner_label": ("GitHub runner label", "text"),
    POWER_FIELD: ("Labgrid power control", "json"),
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

    for name, (label, cf_type) in CUSTOM_FIELDS.items():
        if nb.extras.custom_fields.get(name=name) is None:
            logger.info("creating NetBox custom field %r", name)
            nb.extras.custom_fields.create(
                object_types=["dcim.device"],
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


def power_devices(nb, site_slug: str) -> list[PowerDevice]:
    """The devices at a site that have power outlets, with what each outlet feeds."""
    outlets: dict[int, list] = {}
    for outlet in nb.dcim.power_outlets.filter(site=site_slug):
        outlets.setdefault(outlet.device.id, []).append(outlet)
    if not outlets:
        return []
    found = []
    for device in nb.dcim.devices.filter(id=list(outlets)):
        settings = (device.custom_fields or {}).get(POWER_FIELD)
        ip = getattr(device, "primary_ip", None)
        found.append(
            PowerDevice(
                device.name,
                settings if isinstance(settings, dict) else {},
                ip.address.split("/")[0] if ip else "",
                tuple(
                    PowerOutlet(o.name, ", ".join(_peers(o)) or None)
                    for o in sorted(outlets[device.id], key=lambda o: _natural(o.name))
                ),
            )
        )
    return sorted(found, key=lambda d: d.name)


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


def _create_power_device(nb, name: str, site_id: int, settings: dict):
    power = POWER_TYPES[settings["type"]]
    role = _get_or_create(
        nb.dcim.device_roles, POWER_ROLE_SLUG, name=POWER_ROLE_NAME, color="ff9800"
    )
    mfr = _get_or_create(
        nb.dcim.manufacturers, POWER_MANUFACTURER_SLUG, name=POWER_MANUFACTURER_NAME
    )
    device_type = _get_or_create(
        nb.dcim.device_types,
        f"labgrid-power-{power.key}",
        manufacturer=mfr.id,
        model=power.label,
    )
    logger.info("creating NetBox power device %r", name)
    return nb.dcim.devices.create(
        name=name,
        device_type=device_type.id,
        role=role.id,
        site=site_id,
        custom_fields={POWER_FIELD: settings},
    )


def connect_power(
    nb, board, *, site_slug: str, device: str, settings: dict, outlets: list[str]
) -> list[str]:
    """Cable ``board``'s power to ``outlets`` on power device ``device`` at the board's site.

    The device and its outlets are created if missing; ``settings`` (the
    ``labgrid_power`` value) fill in a device's empty field but never replace
    one. The board's free power ports are used before new ones are added.
    Cables already there stay: an outlet feeding another device is refused
    before anything is written, and the board's other connections are
    reported, not removed. Returns what was done, one line each.
    """
    site = nb.dcim.sites.get(slug=site_slug)
    if site is None:
        raise RuntimeError(f"NetBox site {site_slug!r} does not exist")
    found = list(nb.dcim.devices.filter(name=device, site_id=site.id))
    power_device = found[0] if found else None
    existing = {}
    if power_device is not None:
        existing = {o.name: o for o in nb.dcim.power_outlets.filter(device_id=power_device.id)}
    for name in outlets:
        others = (
            [p for p in _peers(existing[name]) if not p.startswith(f"{board.name} ")]
            if (name in existing)
            else []
        )
        if others:
            raise RuntimeError(
                f"{outlet_label(device, name)} already feeds {', '.join(others)} - pick a free "
                "outlet, or remove that cable in NetBox first"
            )

    done = []
    if power_device is None:
        power_device = _create_power_device(nb, device, site.id, settings)
        done.append(f"created power device {device}")
    else:
        current = (power_device.custom_fields or {}).get(POWER_FIELD)
        if not current:
            power_device.custom_fields[POWER_FIELD] = settings
            power_device.save()
            done.append(f"recorded the labgrid power settings on {device}")
        elif current != settings:
            done.append(
                f"{device} keeps its {POWER_FIELD} settings in NetBox ({current}), "
                f"which differ from this board's ({settings})"
            )

    ports = sorted(nb.dcim.power_ports.filter(device_id=board.id), key=lambda p: _natural(p.name))
    used = {p.id for p in ports if p.cable is not None}
    wanted = {f"{device} {name}" for name in outlets}
    for name in outlets:
        outlet = existing.get(name)
        if outlet is None:
            outlet = nb.dcim.power_outlets.create(device=power_device.id, name=name)
        elif _peers(outlet):
            done.append(f"{board.name} is already connected to {outlet_label(device, name)}")
            continue
        port = next((p for p in ports if p.id not in used), None)
        if port is None:
            names = {p.name for p in ports}
            port_name = next(
                n
                for n in (POWER_PORT, *(f"{POWER_PORT} {i}" for i in range(2, len(ports) + 3)))
                if n not in names
            )
            port = nb.dcim.power_ports.create(device=board.id, name=port_name)
            ports.append(port)
        used.add(port.id)
        nb.dcim.cables.create(
            a_terminations=[{"object_type": "dcim.powerport", "object_id": port.id}],
            b_terminations=[{"object_type": "dcim.poweroutlet", "object_id": outlet.id}],
        )
        done.append(f"connected {board.name} {port.name} to {outlet_label(device, name)}")
    for port in ports:
        for peer in _peers(port):
            if peer not in wanted:
                done.append(
                    f"{board.name} {port.name} is also connected to {peer} - left as is; "
                    "remove that cable in NetBox if the board was moved"
                )
    return done


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
