"""Wrap labgrid-client reservations: reserve by tag filter, acquire, release.

Reserves by tags (not a known place name) and discovers the allocated place
from the reservation, so consumers never name a place.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

from .errors import BoardUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reservation:
    place: str
    token: str


def _filter_args(filt: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in filt.items()]


def _parse_token(stdout: str) -> str | None:
    m = re.search(r"LG_TOKEN=(\S+)", stdout)
    return m.group(1) if m else None


def _parse_allocated_place(stdout: str, token: str) -> str | None:
    """Find the allocated place for `token` in `labgrid-client reservations` output.

    Allocations look like ``main: <exporter>/<place>``; return the bare place.
    """
    in_block = False
    in_allocations = False
    for line in stdout.splitlines():
        if line.startswith("Reservation"):
            in_block = token in line
            in_allocations = False
            continue
        if not in_block:
            continue
        if re.search(r"^\s+allocations:\s*$", line):
            in_allocations = True
            continue
        if re.search(r"^\s+\w[\w-]*:\s*$", line):
            in_allocations = False
            continue
        if in_allocations:
            m = re.search(r":\s*([\w./-]+)\s*$", line)
            if m and "/" in m.group(1):
                return m.group(1).rsplit("/", 1)[-1]
    return None


def reserve_and_acquire(
    coord: str,
    filt: dict[str, str],
    *,
    wait: float,
    client: str = "labgrid-client",
) -> Reservation:
    base = [client, "-x", coord]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, trusted client
            [*base, "reserve", "--shell", "--wait", *_filter_args(filt)],
            capture_output=True,
            text=True,
            timeout=wait,
        )
    except subprocess.TimeoutExpired as e:
        raise BoardUnavailable(f"no free board matching {filt} within {wait:.0f}s") from e
    if proc.returncode != 0:
        raise BoardUnavailable(f"reservation failed for {filt}: {proc.stderr.strip()}")

    token = _parse_token(proc.stdout)
    if not token:
        raise BoardUnavailable(f"could not parse reservation token from: {proc.stdout!r}")

    def _cancel():
        # Best-effort cancel so we don't leak the reservation.
        subprocess.run([*base, "cancel-reservation", token], capture_output=True, text=True)  # noqa: S603

    try:
        res_proc = subprocess.run(  # noqa: S603
            [*base, "reservations"], capture_output=True, text=True, timeout=15
        )
    except subprocess.TimeoutExpired as e:
        _cancel()
        raise BoardUnavailable(f"reservations lookup timed out for {token}") from e
    place = _parse_allocated_place(res_proc.stdout, token)
    if not place:
        _cancel()
        raise BoardUnavailable(f"reservation {token} has no allocated place yet")

    try:
        acq = subprocess.run(  # noqa: S603
            [*base, "-p", f"+{token}", "acquire"], capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired as e:
        _cancel()
        raise BoardUnavailable(f"acquire timed out for place {place}") from e
    if acq.returncode != 0:
        _cancel()
        raise BoardUnavailable(f"acquire failed for place {place}: {acq.stderr.strip()}")

    return Reservation(place=place, token=token)


def release(coord: str, reservation: Reservation, *, client: str = "labgrid-client") -> None:
    """Release the place and cancel the reservation. Never raises."""
    base = [client, "-x", coord]
    for cmd in (
        [*base, "-p", f"+{reservation.token}", "release"],
        [*base, "cancel-reservation", reservation.token],
    ):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=15)  # noqa: S603
        except Exception as e:  # noqa: BLE001 - cleanup must not mask original error
            logger.warning("reservation cleanup step failed (%s): %s", " ".join(cmd), e)
