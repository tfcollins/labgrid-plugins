"""Background HTTP server context manager for serving an SD image.

Used by ``BootZynq7000JTAGRecovery`` to host the SD image the recovery
initramfs ``wget``s. The server runs in a daemon thread and shuts down
cleanly when the context manager exits.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import socketserver
import threading
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler

log = logging.getLogger(__name__)


class _SilentHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that doesn't spam stderr per request."""

    def log_message(self, format, *args):  # noqa: A002  - stdlib signature
        log.debug("HTTP: " + format, *args)


class _ReusableServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


@contextlib.contextmanager
def serve_directory(
    directory: str,
    port: int = 0,
    bind: str = "",
) -> Iterator[tuple[str, int]]:
    """Run a HTTP server in a background thread for the lifetime of the block.

    Args:
        directory: filesystem path to serve.
        port: TCP port to bind. ``0`` (default) picks an ephemeral free
            port — recommended unless the URL needs to be predictable.
        bind: bind address. ``""`` listens on all interfaces, which is
            what a board on a sibling LAN needs.

    Yields:
        ``(host, port)`` of the bound server. ``host`` is the bind
        address as given (caller usually substitutes the real LAN IP).
    """
    # SimpleHTTPRequestHandler accepts a `directory=` kwarg (Python 3.7+),
    # but the ThreadingTCPServer only passes (request, client_address,
    # server). Bind the directory via a lambda factory.
    server = _ReusableServer(
        (bind, port),
        lambda *args, **kw: _SilentHandler(*args, directory=directory, **kw),
    )
    actual_port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever, name=f"adi-recovery-http:{actual_port}", daemon=True
    )
    thread.start()
    log.info("HTTP server serving %s on :%d", directory, actual_port)
    try:
        yield (bind or "0.0.0.0", actual_port)
    finally:
        log.debug("shutting down HTTP server on :%d", actual_port)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def local_ip_for(target_ip: str, fallback: str = "127.0.0.1") -> str:
    """Resolve the local IP the kernel would use to reach ``target_ip``.

    Uses a connected UDP socket trick — no packets are actually sent.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Port doesn't matter; connect() just picks the routing decision.
        s.connect((target_ip, 80))
        return s.getsockname()[0]
    except OSError:
        return fallback
    finally:
        s.close()
