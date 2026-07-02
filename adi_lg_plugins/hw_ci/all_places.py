"""Enumerate every live coordinator place as an infra boot-smoke leg.

Unlike the consumer-driven matrices (request/noos/matlab), this is driven only
by what is live on the coordinator — "boot whatever is live". Each free place
becomes one leg: uri-bootable places (Linux -> iiod) run a real boot via
``adi-lg request --mode uri``; flash-only places (no-os/JTAG, which need consumer
firmware to boot) are reserve-only reachability checks (``--mode reserve``).
Classification is derived from the place's ``boot-strategy`` tag so no coordinator
catalog dependency is introduced.
"""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from adi_lg_plugins.hw_ci.schema import Place

# Boot strategies KNOWN to boot Linux and expose an iiod URI over the network.
# These get a real boot-verify (mode="uri"). Every OTHER strategy — fabric-only
# loads, JTAG recovery, SD reflash, no-os firmware, and anything not yet listed —
# falls through to reserve-only (mode="reserve"), which fails safe: a place that
# cannot answer iiod is acquired + reachability-checked instead of false-failing a
# boot it was never going to pass. Add a strategy here only once it is confirmed to
# serve iiod after boot.
URI_BOOTABLE_STRATEGIES: frozenset[str] = frozenset(
    {
        "BootFPGASoC",
        "BootFPGASoCTFTP",
        "BootFPGASoCSSH",
        "BootTickFPGASSH",
        "BootRPI",
    }
)


@dataclass(frozen=True)
class BootLeg:
    """One infra boot-smoke leg: acquire+boot (or reserve) a single place."""

    place: str
    part: str
    carrier: str
    runner: str | None  # the place's `runner` tag; None -> workflow fallback label
    boot_strategy: str
    mode: str  # "uri" (real boot + iiod verify) or "reserve" (acquire + reachable)

    def as_matrix_dict(self) -> dict:
        return {
            "place": self.place,
            "part": self.part,
            "carrier": self.carrier,
            "runner": self.runner or "",
            "boot_strategy": self.boot_strategy,
            "mode": self.mode,
        }


def host_reachable(host: str, *, port: int = 22, timeout: float = 3.0) -> bool:
    """True if a TCP connect to ``host`` (or ``<host>.local``) on ``port`` succeeds.

    The coordinator names an exporter host by a bare name (e.g. ``nuc``); on many
    lab networks only the mDNS ``<name>.local`` form resolves, so try the bare name
    first and fall back to ``.local``. Any resolve/connect failure yields ``False``.
    """
    for candidate in (host, f"{host}.local"):
        try:
            with socket.create_connection((candidate, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def default_reachable(place: Place, *, port: int = 22, timeout: float = 3.0) -> bool:
    """Reachability predicate for a place, keyed on its exporter host.

    A place whose exporter host is unknown is treated as reachable — we can't probe
    it, so we must not drop it. Otherwise probe the exporter host.
    """
    if not place.exporter:
        return True
    return host_reachable(place.exporter, port=port, timeout=timeout)


def build_all_places_matrix(
    places: Iterable[Place],
    *,
    reachable: Callable[[Place], bool] | None = None,
) -> tuple[list[BootLeg], list[str], list[str]]:
    """Split live places into boot legs + skipped-acquired + skipped-unreachable.

    One leg per FREE, reachable place. Acquired places are returned in ``acquired``
    (contention, not breakage — must not fail the run). When ``reachable`` is given,
    a place whose host it rejects is returned in ``unreachable`` and emits no leg —
    this keeps a board whose host is offline from producing a leg that would queue
    forever on a runner that will never come online. When ``reachable`` is ``None``,
    no reachability filtering happens (every free place gets a leg).
    """
    legs: list[BootLeg] = []
    acquired: list[str] = []
    unreachable: list[str] = []
    for place in places:
        if place.is_acquired:
            acquired.append(place.name)
            continue
        if reachable is not None and not reachable(place):
            unreachable.append(place.name)
            continue
        mode = "uri" if place.boot_strategy in URI_BOOTABLE_STRATEGIES else "reserve"
        legs.append(
            BootLeg(
                place=place.name,
                part=place.daughter_board,
                carrier=place.carrier,
                runner=place.extra_tags.get("runner"),
                boot_strategy=place.boot_strategy,
                mode=mode,
            )
        )
    return legs, acquired, unreachable
