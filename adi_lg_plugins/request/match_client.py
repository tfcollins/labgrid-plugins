"""HTTP client for the coordinator's /api/match and /api/catalog endpoints.

Uses only the standard library (urllib) to avoid adding a dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class MatchCandidate:
    place: str
    carrier: str
    acquired: bool


@dataclass(frozen=True)
class MatchResult:
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    matlab_boards: dict[str, str] = field(default_factory=dict)
    candidates: list[MatchCandidate] = field(default_factory=list)


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
    mode: str = "uri",
    bootfile: str | None = None,
    timeout: float = 15.0,
) -> MatchResult:
    params = {"part": part, "mode": mode}
    if carrier:
        params["carrier"] = carrier
    if bootfile:
        params["bootfile"] = bootfile
    url = f"{_base_url(coord)}/api/match?{urlencode(params)}"
    data = _get_json(url, timeout=timeout)
    return MatchResult(
        satisfiable=bool(data.get("satisfiable")),
        reason=data.get("reason", ""),
        reservation_filter=data.get("reservation_filter") or {},
        version=data.get("version"),
        matlab_boards=data.get("matlab_boards") or {},
        candidates=[
            MatchCandidate(
                place=c["place"], carrier=c.get("carrier", ""), acquired=c.get("acquired", False)
            )
            for c in (data.get("candidates") or [])
        ],
    )
