"""Client-side orchestration for the hardware-request layer (uri mode).

Flow: resolve coordinator -> GET /match -> reserve+acquire (labgrid, queues
if busy) -> find the concrete place -> render env -> boot to shell -> resolve
URI -> yield Lease -> on exit: optional power-down, then release (always).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..hw_ci.coordinator import list_live_places, resolve_coordinator
from ..hw_ci.render_env import render_env_to
from ..hw_ci.schema import Place
from . import match_client, reservation
from .errors import NoMatchingBoard, ProvisionError
from .uri import resolve_uri

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """A booted board handle yielded by ``request()``.

    ``target`` is the live labgrid Target; its drivers are deactivated and
    the coordinator reservation released when the ``with`` block exits.
    ``uri`` is the primary handover for pyadi-iio (uri mode). ``console`` is
    the serial console handle for flash mode (no-os firmware); exactly one of
    ``uri`` / ``console`` is set depending on the request mode.
    """

    place: str
    carrier: str
    tags: dict[str, str] = field(default_factory=dict)
    uri: str | None = None
    console: Any = None
    target: Any = None


def _resolve_api(coord: str) -> str:
    """REST API base (host:port) for /api/match + /api/places.

    The REST API and the gRPC coordinator are separate services on different
    ports (8000 vs 20408). Honor an explicit ADI_LG_API / LG_API override;
    otherwise default to the coordinator host on port 8000.
    """
    explicit = os.environ.get("ADI_LG_API") or os.environ.get("LG_API")
    if explicit:
        return explicit
    base = coord.split("://", 1)[-1]
    host = base.rsplit(":", 1)[0] if ":" in base else base
    return f"{host}:8000"


def _concrete_place(coord: str, name: str) -> Place:
    """Return the validated hw_ci Place for `name` from the coordinator."""
    places, _skipped = list_live_places(coord)
    for p in places:
        if p.name == name:
            return p
    raise ProvisionError(f"acquired place '{name}' not found among live places")


def _render_env(place, **kw) -> str:
    out = Path(tempfile.mkdtemp(prefix="adi-lg-req-")) / "env.yaml"
    render_env_to(place, out, **kw)
    return str(out)


def _boot(
    env_path: str, strategy_name: str, *, image: str | None, target_name: str = "main"
) -> Any:
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


def _get_console(target: Any) -> Any:
    """Return the board's serial console driver (flash mode handover), or None.

    no-os firmware has no network URI — the serial console is the handle a
    consumer reads (e.g. to drive a libiio-over-serial probe). Best-effort.
    """
    try:
        return target.get_driver("ADIShellDriver")
    except Exception as e:  # noqa: BLE001 - console handle is best-effort
        logger.warning("could not resolve console driver: %s", e)
        return None


def _power_off(target: Any, strategy_name: str) -> None:
    """Best-effort power-down via the strategy's powered_off transition.

    Never raises: power-down is a courtesy on exit and must not mask the
    user's result or block the subsequent release.
    """
    try:
        target.get_driver(strategy_name).transition("powered_off")
    except Exception as e:  # noqa: BLE001 - power-down is best-effort
        logger.warning("power_down requested but power-off failed: %s", e)


def _cleanup_target(target: Any) -> None:
    """Best-effort teardown of the in-process labgrid target (deactivate
    drivers, close console/network). Never raises."""
    try:
        target.cleanup()
    except Exception as e:  # noqa: BLE001 - teardown is best-effort
        logger.warning("target cleanup failed: %s", e)


def _remove_env_dir(env_path: str) -> None:
    """Remove the temp dir created by _render_env. Guarded by our prefix so a
    monkeypatched or foreign path is never touched. Never raises."""
    parent = Path(env_path).parent
    if parent.name.startswith("adi-lg-req-"):
        shutil.rmtree(parent, ignore_errors=True)


@contextmanager
def request(
    *,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
    firmware: str | None = None,
    bitstream: str | None = None,
    ps7_init: str | None = None,
    validate: str | None = None,
    wait: float = 1800.0,
    coord: str | None = None,
    power_down: bool = False,
    target_name: str = "main",
    **filters: str,
):
    """Request a board, provision it, yield a Lease, and release on exit.

    ``mode='uri'`` boots a Kuiper image and hands over a network libIIO URI.
    ``mode='flash'`` JTAG-flashes a no-os firmware ``.elf`` (``firmware``,
    required) onto the board, validates a serial banner (``validate``, default
    the IIOD banner), and hands over the serial console (``uri`` is None).
    """
    if mode not in ("uri", "flash"):
        raise NotImplementedError(f"mode '{mode}' is not available (uri | flash)")
    if mode == "flash" and not firmware:
        raise ProvisionError("flash mode requires a firmware .elf (firmware=...)")
    if filters:
        raise NotImplementedError(
            f"extra filters {sorted(filters)} are not supported yet "
            "(only part + carrier narrow the match)"
        )

    coord = resolve_coordinator(coord)
    api = _resolve_api(coord)
    match = match_client.get_match(api, part=part, carrier=carrier, bootfile=bootfile, mode=mode)
    if not match.satisfiable:
        raise NoMatchingBoard(match.reason or f"no board for part '{part}'")

    res = reservation.reserve_and_acquire(coord, match.reservation_filter, wait=wait)
    target = None
    env_path = None
    strategy_name = match.strategy or ""
    try:
        place = _concrete_place(api, res.place)
        if mode == "flash":
            # The flash strategy comes from the catalog (BootNoOSJTAG) and
            # overrides the place's boot-strategy tag; render that template and
            # inject the per-build artifact paths + validation banner.
            strategy_name = match.strategy or "BootNoOSJTAG"
            subs = {"firmware_elf": firmware}
            if bitstream:
                subs["bitstream_path"] = bitstream
            if ps7_init:
                subs["ps7_init_tcl"] = ps7_init
            if validate:
                subs["boot_marker"] = validate
            env_path = _render_env(place, strategy=strategy_name, extra_subs=subs)
            target = _boot(env_path, strategy_name, image=None, target_name=target_name)
            console = _get_console(target)
            uri = None
        else:
            # The live place's boot-strategy tag is the authority for the driver
            # name the rendered env defines; match.strategy (parsed for metadata)
            # should equal it.
            strategy_name = place.boot_strategy
            env_path = _render_env(place)
            target = _boot(env_path, strategy_name, image=match.image, target_name=target_name)
            console = None
            uri = resolve_uri(target)
        yield Lease(
            place=res.place,
            carrier=place.carrier,
            # tags mirror the labgrid place tags for consumers that iterate tags
            # generically; `carrier` is duplicated as a first-class field for
            # convenience — both are intentional, keep them.
            tags={
                "daughter-board": place.daughter_board,
                "carrier": place.carrier,
                "boot-strategy": strategy_name,
            },
            uri=uri,
            console=console,
            target=target,
        )
    finally:
        if power_down and target is not None:
            _power_off(target, strategy_name)
        if target is not None:
            _cleanup_target(target)
        reservation.release(coord, res)
        if env_path:
            _remove_env_dir(env_path)
