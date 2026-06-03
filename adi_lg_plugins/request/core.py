"""Client-side orchestration for the hardware-request layer (uri mode).

Flow: resolve coordinator -> GET /match -> reserve+acquire (labgrid, queues
if busy) -> find the concrete place -> render env -> boot to shell -> resolve
URI -> yield Lease -> on exit: optional power-down, then release (always).
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
    """A booted board handle yielded by ``request()``.

    ``target`` is the live labgrid Target; it is only valid inside the
    ``with`` block and is released when the block exits. ``uri`` is the
    primary handover for pyadi-iio. ``console`` is reserved for the future
    flash mode and is always None here.
    """

    place: str
    carrier: str
    tags: dict[str, str] = field(default_factory=dict)
    uri: str | None = None
    console: Any = None
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


def _boot(env_path: str, strategy_name: str, *, image: str | None, target_name: str = "main"):
    """Boot the board to a Linux shell and return the labgrid target."""
    from labgrid import Environment

    env = Environment(env_path)
    tg = env.get_target(target_name)
    if image:
        try:
            res = tg.get_resource("KuiperRelease")
            res.release_version = image
            logger.info("Using image version %s", image)
        except Exception:  # noqa: BLE001 - resource may be absent for some boards
            logger.warning("no KuiperRelease resource to pin image %s", image)
    strategy = tg.get_driver(strategy_name)
    try:
        strategy.transition("shell")
    except Exception as e:  # noqa: BLE001 - normalise any strategy error
        raise ProvisionError(f"boot failed: {e}") from e
    return tg


def _power_off(target: Any, strategy_name: str) -> None:
    """Best-effort power-down via the strategy's powered_off transition.

    Never raises: power-down is a courtesy on exit and must not mask the
    user's result or block the subsequent release.
    """
    try:
        target.get_driver(strategy_name).transition("powered_off")
    except Exception as e:  # noqa: BLE001 - power-down is best-effort
        logger.warning("power_down requested but power-off failed: %s", e)


@contextmanager
def request(
    *,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
    wait: float = 1800.0,
    coord: str | None = None,
    power_down: bool = False,
    target_name: str = "main",
    **filters: str,
):
    """Request a board, boot it, yield a Lease, and release on exit.

    Only ``mode='uri'`` is supported in this increment.
    """
    if mode != "uri":
        raise NotImplementedError(f"mode '{mode}' is not available yet (uri only)")
    if filters:
        raise NotImplementedError(
            f"extra filters {sorted(filters)} are not supported yet "
            "(only part + carrier narrow the match)"
        )

    coord = resolve_coordinator(coord)
    match = match_client.get_match(coord, part=part, carrier=carrier, bootfile=bootfile)
    if not match.satisfiable:
        raise NoMatchingBoard(match.reason or f"no board for part '{part}'")

    res = reservation.reserve_and_acquire(coord, match.reservation_filter, wait=wait)
    target = None
    strategy_name = match.strategy or ""
    try:
        place = _concrete_place(coord, res.place)
        strategy_name = place.boot_strategy
        env_path = _render_env(place)
        target = _boot(env_path, strategy_name, image=match.image, target_name=target_name)
        uri = resolve_uri(target)
        yield Lease(
            place=res.place,
            carrier=place.carrier,
            tags={
                "daughter-board": place.daughter_board,
                "carrier": place.carrier,
                "boot-strategy": strategy_name,
            },
            uri=uri,
            target=target,
        )
    finally:
        if power_down and target is not None:
            _power_off(target, strategy_name)
        reservation.release(coord, res)
