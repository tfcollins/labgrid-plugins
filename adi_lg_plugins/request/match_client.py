"""HTTP client for the coordinator's /api/match endpoint (Plan 1 contract).

Uses only the standard library (urllib) to avoid adding a dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class MatchResult:
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = field(default_factory=dict)
    image: str | None = None
    strategy: str | None = None
    place: str | None = None


def _base_url(coord: str) -> str:
    """Turn a coordinator reference (host:port or full URL) into an http base URL.

    The coordinator REST API listens on the API port; callers pass the
    host:port of that API (e.g. ``10.0.0.41:8000``).
    """
    if coord.startswith(("http://", "https://")):
        return coord.rstrip("/")
    return f"http://{coord.rstrip('/')}"


def _get_json(url: str, timeout: float = 15.0) -> dict:
    with urlopen(url, timeout=timeout) as resp:  # noqa: S310 - trusted lab URL
        return json.loads(resp.read().decode("utf-8"))


def get_match(
    coord: str,
    *,
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
    timeout: float = 15.0,
) -> MatchResult:
    params = {"part": part}
    if carrier:
        params["carrier"] = carrier
    if bootfile:
        params["bootfile"] = bootfile
    url = f"{_base_url(coord)}/api/match?{urlencode(params)}"
    data = _get_json(url, timeout=timeout)
    return MatchResult(
        satisfiable=bool(data.get("satisfiable")),
        reason=data.get("reason") or "",
        reservation_filter=data.get("reservation_filter") or {},
        image=data.get("image"),
        strategy=data.get("strategy"),
        place=data.get("place"),
    )
