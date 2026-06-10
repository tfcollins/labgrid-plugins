"""Resolve a booted target's libIIO URI and verify the iiod endpoint accepts connections."""

from __future__ import annotations

import socket
import time
from typing import Any

from .errors import ProvisionError

IIOD_PORT = 30431  # libiio network daemon's fixed TCP port


def verify_iio_context(
    uri: str,
    *,
    port: int = IIOD_PORT,
    timeout: float = 60.0,
    interval: float = 2.0,
) -> None:
    """Boot-verification gate: prove iiod is accepting connections at ``uri``.

    A board can reach a shell with iiod dead; that must surface as a distinct
    boot failure, not a wall of downstream test errors. Polls a plain TCP
    connect until ``timeout`` — dependency-free on purpose (CI runners have no
    pylibiio). Non-``ip:`` URIs are not probeable and pass through.
    """
    if not uri.startswith("ip:"):
        return
    host = uri[3:]
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while True:
        try:
            attempt_timeout = min(5.0, max(deadline - time.monotonic(), 0.1))
            with socket.create_connection((host, port), timeout=attempt_timeout):
                return
        except OSError as e:
            last_err = e
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)
    raise ProvisionError(
        f"boot verification failed: iiod not reachable at {host}:{port} "
        f"within {timeout:.0f}s ({last_err})"
    )


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
