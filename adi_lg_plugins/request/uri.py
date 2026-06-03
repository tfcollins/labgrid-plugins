"""Resolve a booted target's libIIO URI from its NetworkService resource."""

from __future__ import annotations

from typing import Any

from .errors import ProvisionError


def resolve_uri(target: Any) -> str:
    """Return ``ip:<address>`` from the target's NetworkService resource.

    Mirrors the resolution used by the MCP server (tools/mcp.py).
    """
    try:
        net = target.get_resource("NetworkService")
    except Exception as e:  # noqa: BLE001 - target raises a bare Exception when absent
        raise ProvisionError(f"no NetworkService resource on booted target: {e}") from e
    address = getattr(net, "address", None)
    if not address:
        raise ProvisionError("booted target's NetworkService has no address")
    return f"ip:{address}"
