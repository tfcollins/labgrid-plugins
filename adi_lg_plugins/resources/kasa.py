import os

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource


@target_factory.reg_resource
@attr.s(eq=False)
class KasaOutlet(Resource):
    """The KasaOutlet describes a TP-Link Kasa smart plug or power strip.

    The driver controls the device over the local network with the
    ``python-kasa`` library (no cloud round-trip). A single plug is
    controlled as one outlet; a power strip exposes each socket as a child
    that can be selected by index or alias via ``outlets``.

    Newer Kasa devices (KLAP/SMART protocol) require TP-Link account
    credentials even for local control; legacy devices do not. ``username``
    and ``password`` default to the ``KASA_USERNAME`` / ``KASA_PASSWORD``
    environment variables and may be left unset for legacy devices.

    Args:
        host (str): IP address or hostname of the Kasa device.
        outlets (str): Optional comma-separated list of child sockets to
            control on a power strip, each a 0-based index or a socket
            alias. If None, a strip's sockets are all controlled together
            and a single plug is controlled directly.
        username (str): Optional TP-Link account username (email). Defaults
            to the ``KASA_USERNAME`` environment variable.
        password (str): Optional TP-Link account password. Defaults to the
            ``KASA_PASSWORD`` environment variable.
        delay (float, default=5.0): delay between power off and power on
            during a reset/cycle operation.
    """

    host = attr.ib(validator=attr.validators.instance_of(str))
    outlets = attr.ib(
        default=None, validator=attr.validators.optional(attr.validators.instance_of(str))
    )
    username = attr.ib(
        default=attr.Factory(lambda: os.environ.get("KASA_USERNAME")),
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    password = attr.ib(
        default=attr.Factory(lambda: os.environ.get("KASA_PASSWORD")),
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))
