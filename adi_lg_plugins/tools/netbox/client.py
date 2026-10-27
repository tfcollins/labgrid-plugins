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
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import requests
import urllib3

logger = logging.getLogger(__name__)

DEVICE_ROLE_SLUG = "labgrid-target"
DEVICE_ROLE_NAME = "Labgrid Target"
MANUFACTURER_SLUG = "adi-lab"
MANUFACTURER_NAME = "Analog Devices, Inc. (lab hardware)"

# custom field name -> (label, NetBox field type)
CUSTOM_FIELDS: dict[str, tuple[str, str]] = {
    "carrier": ("Carrier", "text"),
    "daughter_board": ("Daughter board / chip", "text"),
    "boot_strategy": ("Boot strategy", "text"),
    "exporter_host": ("Exporter SSH target", "text"),
    "runner_label": ("GitHub runner label", "text"),
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


def connect(url: str, token: str, *, verify: bool | str = True):
    """Return a connected ``pynetbox.api`` instance.

    ``verify`` is requests' TLS setting: ``False`` skips certificate checks, a
    path names a CA bundle (for a NetBox behind an internal CA).
    """
    pynetbox = _require_pynetbox()
    nb = pynetbox.api(url, token=token)
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
            "the system trust store is /etc/ssl/certs/ca-certificates.crt), or "
            "--netbox-insecure to skip verification"
        ) from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"could not reach NetBox at {url}: {e}") from e
    except pynetbox.RequestError as e:
        hint = ""
        if e.req.status_code in (401, 403):
            hint = " - check the API token (--netbox-token / NETBOX_TOKEN)"
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
