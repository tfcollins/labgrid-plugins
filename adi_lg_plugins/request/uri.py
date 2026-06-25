"""Resolve a booted target's libIIO URI and verify the iiod endpoint accepts connections."""

from __future__ import annotations

import logging
import socket
import time
from typing import Any

from .errors import ProvisionError

IIOD_PORT = 30431  # libiio network daemon's fixed TCP port

logger = logging.getLogger(__name__)


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


def resolve_uri(target: Any, *, wait: float = 90.0, interval: float = 3.0) -> str:
    """Return ``ip:<address>`` for the booted target.

    Prefer the DUT's live ``eth0`` IP read over the shell: the board DHCPs a
    fresh address every boot, so the exporter's static ``NetworkService.address``
    is unreliable.

    Polls the live-IP shell query until a non-empty address is returned or
    ``wait`` seconds elapse (DHCP race: boards reach a shell prompt before the
    lease lands).  At least one attempt is always made.  Falls back to the
    static ``NetworkService.address`` on deadline, with a warning that it may
    be stale.
    """
    deadline = time.monotonic() + wait
    while True:
        for drv in ("ADIShellDriver", "ShellDriver"):
            try:
                shell = target.get_driver(drv)
                out, _err, rc = shell.run(
                    "ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1"
                )
                if rc == 0 and out and out[0].strip():
                    return f"ip:{out[0].strip()}"
            except Exception:  # noqa: BLE001 - fall back to the static address
                pass
        if time.monotonic() >= deadline:
            break
        time.sleep(interval)

    try:
        net = target.get_resource("NetworkService")
    except Exception as e:  # noqa: BLE001 - target raises a bare Exception when absent
        raise ProvisionError(f"no NetworkService resource on booted target: {e}") from e
    address = getattr(net, "address", None)
    if not address:
        raise ProvisionError("booted target's NetworkService has no address")
    logger.warning(
        "live eth0 IP not readable after %.0fs; falling back to static"
        " NetworkService.address %s (may be stale)",
        wait,
        address,
    )
    return f"ip:{address}"
