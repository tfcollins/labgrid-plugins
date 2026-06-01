"""Resolve UART + JTAG connection facts off a booted labgrid place.

The bash / non-Python HW-CI pattern boots a board with ``adi-lg boot-*``
and then hands off to an external test driver that talks to the DUT over
the serial console (UART) and ``xsdb`` (JTAG) — not over a libIIO URI or
SSH. This module reads those facts off a labgrid target *after* boot and
renders them as ``KEY=VALUE`` lines a shell step can consume.

It mirrors the idiom of the (removed) ``matlab_ci/run.py`` bridge: pure
functions plus an injected ``env_factory`` (defaulting to a lazily
imported :class:`labgrid.Environment`) so the logic is unit-tested
without hardware or a labgrid install. Place reservation (acquire /
release) is handled one layer up in CI, not here.

See :doc:`/user-guide/hw-ci-bash`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# Serial console resource classes, most-specific first. A RemotePlace
# (coordinator path) re-exposes the console as a NetworkSerialPort
# (host + TCP socket port); a runner-local exporter uses RawSerialPort /
# USBSerialPort with a /dev/ttyUSBx path.
_SERIAL_CANDIDATES = ("RawSerialPort", "USBSerialPort", "NetworkSerialPort")
_JTAG_CANDIDATES = ("XilinxDeviceJTAG",)
_TOOL_CANDIDATES = ("XilinxVivadoTool",)


@dataclass(frozen=True)
class ResolvedResources:
    """UART + JTAG facts read off a booted target.

    ``uart_device`` is set for a runner-local serial port (a ``/dev/...``
    path); ``uart_host`` / ``uart_port`` are set for a coordinator-side
    ``NetworkSerialPort`` (a TCP socket). Exactly one of those shapes is
    populated for a given place. JTAG fields carry what a bash ``xsdb``
    invocation actually needs — the binary path and the target indices;
    there is no cable-serial attribute in the ADI resource set.
    """

    uart_device: str | None = None
    uart_host: str | None = None
    uart_port: int | None = None
    uart_speed: int | None = None
    jtag_xsdb: str | None = None
    jtag_root_target: int | None = None
    jtag_mb_target: int | None = None


def _first_resource(target: Any, names: tuple[str, ...]) -> Any | None:
    """Return the first resolvable resource among ``names`` (or None).

    ``target.get_resource`` accepts a class-name string; it raises when
    the resource is absent or ambiguous, so each candidate is tried in
    turn and failures are swallowed.
    """
    for name in names:
        try:
            res = target.get_resource(name)
        except Exception:
            continue
        if res is not None:
            return res
    return None


def _is_network(res: Any) -> bool:
    """True if the serial resource is a network proxy (carries ``host``).

    Matches the "iterate resources, look for ``host``" idiom in
    :mod:`adi_lg_plugins.drivers.xilinxjtagdriver`.
    """
    return getattr(res, "host", None) is not None


def resolve_resources(target: Any) -> ResolvedResources:
    """Read UART + JTAG facts off a (post-boot) labgrid target."""
    serial = _first_resource(target, _SERIAL_CANDIDATES)
    jtag = _first_resource(target, _JTAG_CANDIDATES)
    tool = _first_resource(target, _TOOL_CANDIDATES)

    uart_device = uart_host = uart_port = uart_speed = None
    if serial is not None:
        uart_speed = getattr(serial, "speed", None)
        if _is_network(serial):
            uart_host = getattr(serial, "host", None)
            uart_port = getattr(serial, "port", None)
        else:
            uart_device = getattr(serial, "port", None)

    return ResolvedResources(
        uart_device=uart_device,
        uart_host=uart_host,
        uart_port=uart_port,
        uart_speed=uart_speed,
        jtag_xsdb=getattr(tool, "xsdb_path", None),
        jtag_root_target=getattr(jtag, "root_target", None),
        jtag_mb_target=getattr(jtag, "microblaze_target", None),
    )


def render_github_output(r: ResolvedResources) -> str:
    """Render set fields as ``KEY=VALUE`` lines for ``$GITHUB_OUTPUT``.

    Only fields that are set are emitted, so a board with no JTAG (or a
    network-only console) produces just the keys that apply.
    """
    pairs = (
        ("LG_UART_DEVICE", r.uart_device),
        ("LG_UART_HOST", r.uart_host),
        ("LG_UART_PORT", r.uart_port),
        ("LG_UART_SPEED", r.uart_speed),
        ("LG_JTAG_XSDB", r.jtag_xsdb),
        ("LG_JTAG_ROOT_TARGET", r.jtag_root_target),
        ("LG_JTAG_MB_TARGET", r.jtag_mb_target),
    )
    lines = [f"{key}={value}" for key, value in pairs if value is not None]
    return "".join(f"{line}\n" for line in lines)


def resolve_from_env(
    config: str,
    *,
    target_name: str = "main",
    env_factory: Callable[[str], Any] | None = None,
) -> ResolvedResources:
    """Load a rendered env yaml, get its target, and resolve resources.

    ``env_factory`` defaults to :class:`labgrid.Environment` (imported
    lazily so importing this module never requires labgrid); it is
    injected in tests.
    """
    if env_factory is None:
        from labgrid import Environment  # lazy: only needed for real runs

        env_factory = Environment

    env = env_factory(str(config))
    target = env.get_target(target_name)
    return resolve_resources(target)
