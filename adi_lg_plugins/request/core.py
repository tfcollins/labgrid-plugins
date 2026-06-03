"""Client-side orchestration for the hardware-request layer (uri mode).

Flow: resolve coordinator -> GET /match -> reserve+acquire (labgrid) ->
fetch concrete place -> render env -> boot -> resolve URI -> yield Lease ->
release on exit (always).
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..hw_ci.coordinator import list_live_places, resolve_coordinator
from ..hw_ci.render_env import render_env_to
from . import match_client, reservation
from .errors import NoMatchingBoard, ProvisionError
from .uri import resolve_uri

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    place: str
    carrier: str
    tags: dict[str, str] = field(default_factory=dict)
    uri: str | None = None
    matlab_board: str | None = None
    console: Any = None  # Phase 3 (flash mode); always None in Phase 1
    target: Any = None


def _concrete_place(coord: str, name: str):
    """Return the validated hw_ci Place for `name` from the coordinator."""
    places, _skipped = list_live_places(coord)
    for p in places:
        if p.name == name:
            return p
    raise ProvisionError(f"acquired place '{name}' not found among live places")


def _render_env(place) -> str:
    out = Path(tempfile.mkdtemp(prefix="adi-lg-req-")) / "env.yaml"
    render_env_to(place, out)
    return str(out)


def _boot(env_path: str, strategy_name: str, *, version: str | None, target_name: str = "main"):
    """Boot the board to a Linux shell and return the labgrid target."""
    from labgrid import Environment

    env = Environment(env_path)
    tg = env.get_target(target_name)
    if version:
        try:
            res = tg.get_resource("KuiperRelease")
            res.release_version = version
            logger.info("Using image version %s", version)
        except Exception:  # noqa: BLE001 - resource may be absent for some boards
            logger.warning("no KuiperRelease resource to pin version %s", version)
    strategy = tg.get_driver(strategy_name)
    try:
        strategy.transition("shell")
    except Exception as e:  # noqa: BLE001 - normalise any strategy error
        raise ProvisionError(f"boot failed: {e}") from e
    return tg


@contextmanager
def request(
    *,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
    wait: float = 1800.0,
    coord: str | None = None,
    target_name: str = "main",
    **filters: str,
):
    """Request a board, boot it, yield a Lease, and release on exit.

    Phase 1 supports ``mode='uri'`` only.
    """
    if mode != "uri":
        raise NotImplementedError(f"mode '{mode}' is not available in Phase 1 (uri only)")

    coord = resolve_coordinator(coord)
    match = match_client.get_match(coord, part=part, carrier=carrier, mode=mode, bootfile=bootfile)
    if not match.satisfiable:
        raise NoMatchingBoard(match.reason or f"no board for part '{part}'")

    res = reservation.reserve_and_acquire(coord, match.reservation_filter, wait=wait)
    try:
        place = _concrete_place(coord, res.place)
        env_path = _render_env(place)
        target = _boot(
            env_path, place.boot_strategy, version=match.version, target_name=target_name
        )
        uri = resolve_uri(target)
        lease = Lease(
            place=res.place,
            carrier=place.carrier,
            tags={"daughter-board": place.daughter_board, "carrier": place.carrier},
            uri=uri,
            matlab_board=match.matlab_boards.get(place.carrier),
            target=target,
        )
        yield lease
    finally:
        reservation.release(coord, res)
