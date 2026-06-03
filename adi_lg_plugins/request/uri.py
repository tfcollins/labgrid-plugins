"""Resolve a booted target's libIIO URI from its NetworkService resource."""

from __future__ import annotations

from typing import Any

from .errors import ProvisionError


def resolve_uri(target: Any) -> str:
    """Return ``ip:<address>`` for the booted target.

    Prefer the DUT's live ``eth0`` IP read over the shell: the board DHCPs a
    fresh address every boot, so the exporter's static ``NetworkService.address``
    is unreliable. Fall back to the static address if the shell query fails.
    """
    for drv in ("ADIShellDriver", "ShellDriver"):
        try:
            shell = target.get_driver(drv)
            out, _err, rc = shell.run("ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1")
            if rc == 0 and out and out[0].strip():
                return f"ip:{out[0].strip()}"
        except Exception:  # noqa: BLE001 - fall back to the static address
            pass
    try:
        net = target.get_resource("NetworkService")
    except Exception as e:  # noqa: BLE001 - target raises a bare Exception when absent
        raise ProvisionError(f"no NetworkService resource on booted target: {e}") from e
    address = getattr(net, "address", None)
    if not address:
        raise ProvisionError("booted target's NetworkService has no address")
    return f"ip:{address}"
