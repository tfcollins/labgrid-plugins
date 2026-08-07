"""Coordinator-side discovery — list live places with HW-CI tags.

Prefers the coordinator's REST API (``/api/places``, returning JSON
with structured tags). Falls back to ``labgrid-client places`` +
``show`` per-place, parsing the text format, for older coordinators
that don't expose the JSON endpoint yet.

Returns validated :class:`~adi_lg_plugins.hw_ci.schema.Place` objects.
Invalid places are *skipped* with a warning so a single misconfigured
exporter doesn't kill the whole discovery — emit the warning and move
on so the matrix still builds from the well-formed places.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import subprocess
import sys
import urllib.request
from collections.abc import Iterable

from .schema import (
    Place,
    PlaceValidationError,
    validate_place,
)

logger = logging.getLogger(__name__)


def _api_url(coord: str) -> str:
    """Translate ``host:port`` to ``http://host:port`` (idempotent)."""
    if coord.startswith(("http://", "https://")):
        return coord.rstrip("/")
    return f"http://{coord.rstrip('/')}"


def _fetch_places_rest(coord: str, timeout: float = 15.0) -> list[dict]:
    """GET /api/places. Raises on transport / decode errors."""
    url = f"{_api_url(coord)}/api/places"
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
        return json.load(r)


def _fetch_places_cli(coord: str, timeout: float = 15.0) -> list[dict]:
    """Fallback path: shell out to ``labgrid-client``.

    Mirrors the parsing already in ``adi_lg_plugins.tools.mcp:_list_places``
    but returns the same dict shape the REST path does so the rest of
    the pipeline can ignore which path was taken.
    """
    list_out = subprocess.check_output(
        ["labgrid-client", "-x", coord, "places"],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    places: list[dict] = []
    for line in list_out.splitlines():
        name = line.strip()
        if not name:
            continue
        try:
            show = subprocess.check_output(
                ["labgrid-client", "-x", coord, "-p", name, "show"],
                text=True,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        except subprocess.SubprocessError:
            continue
        tags: dict[str, str] = {}
        acquired: str | None = None
        for ln in show.splitlines():
            ln = ln.strip()
            if ln.startswith("tags:"):
                # "tags: foo=bar, baz=qux"
                for kv in ln[len("tags:") :].split(","):
                    kv = kv.strip()
                    if "=" in kv:
                        k, v = kv.split("=", 1)
                        tags[k.strip()] = v.strip()
            elif ln.startswith("acquired:"):
                val = ln[len("acquired:") :].strip()
                acquired = None if val == "None" else val
        places.append({"name": name, "tags": tags, "acquired": acquired})
    return places


def fetch_raw_places(
    coord: str,
    *,
    timeout: float = 15.0,
    force_cli: bool = False,
) -> list[dict]:
    """Try REST first, fall back to CLI on transport failure.

    ``coord`` is the gRPC coordinator address (``host:20408``); the REST
    API lives on a different port, so the REST path queries
    ``_resolve_api(coord)`` (``host:8000``, or the ADI_LG_API / LG_API
    override). Set ``force_cli=True`` to skip the REST path entirely
    (useful when the coordinator hasn't exposed the JSON endpoint yet).
    """
    if not force_cli:
        try:
            return _fetch_places_rest(_resolve_api(coord), timeout=timeout)
        except (OSError, http.client.HTTPException, json.JSONDecodeError, ValueError) as e:
            # Any transport failure (connect refused, timeout, bad JSON, or a
            # garbled BadStatusLine from a non-HTTP service if someone points
            # an ADI_LG_API/LG_API override at the wrong port) is treated the
            # same way — fall through to the labgrid-client CLI path,
            # which is the canonical interface.
            logger.warning(
                "coordinator REST /api/places failed (%s: %s); falling back to labgrid-client",
                type(e).__name__,
                e,
            )
    return _fetch_places_cli(coord, timeout=timeout)


def list_live_places(
    coord: str,
    *,
    timeout: float = 15.0,
    force_cli: bool = False,
    known_strategies: Iterable[str] | None = None,
) -> tuple[list[Place], list[tuple[str, str]]]:
    """Validated places + a list of (name, reason) for the rest.

    The return shape is two lists so the caller can both build the
    matrix (from ``places``) AND surface a clear annotation for the
    skipped exporters (from ``skipped``).
    """
    raw = fetch_raw_places(coord, timeout=timeout, force_cli=force_cli)
    places: list[Place] = []
    skipped: list[tuple[str, str]] = []
    for r in raw:
        try:
            places.append(validate_place(r, known_strategies=known_strategies))
        except PlaceValidationError as e:
            skipped.append((r.get("name", "<unnamed>"), str(e)))
    return places, skipped


def _validate_coordinator_port(coord: str) -> None:
    from urllib.parse import urlparse

    url = coord
    if "://" not in url:
        url = "tcp://" + url
    try:
        parsed = urlparse(url)
        port = parsed.port
        if port is not None and not (0 <= port <= 65535):
            raise ValueError(f"Port out of range 0-65535: {port}")
    except ValueError as e:
        raise ValueError(f"Invalid coordinator address {coord!r}: {e}") from e


def resolve_coordinator(explicit: str | None = None) -> str:
    """Resolve the coordinator URL from arg / env, in order:

    1. ``explicit`` arg if non-empty
    2. ``LG_COORDINATOR`` env var
    3. ``ADI_LG_COORDINATOR`` env var (the convention org-wide vars use)

    Raises :class:`RuntimeError` if none of them are set.
    """
    for src in (explicit, os.environ.get("LG_COORDINATOR"), os.environ.get("ADI_LG_COORDINATOR")):
        if src:
            _validate_coordinator_port(src)
            return src
    raise RuntimeError(
        "no coordinator URL — pass --coord, or set LG_COORDINATOR / "
        "ADI_LG_COORDINATOR in the environment"
    )


def warn_if_rest_port(coord: str) -> None:
    """Warn when the coordinator address carries the REST port ``:8000``.

    ``LG_COORDINATOR`` must be the gRPC coordinator (e.g. ``host:20408``); a
    value ending in ``:8000`` is the REST API port, which passes discovery but
    fails at gRPC reservation. Emits a GitHub ``::warning::`` under Actions,
    else a stderr ``warning:`` line. Inspection only — never raises.
    """
    base = coord.split("://", 1)[-1]
    port = base.rsplit(":", 1)[-1] if ":" in base else ""
    if port != "8000":
        return
    msg = (
        f"coordinator {coord!r} uses the REST port :8000 — LG_COORDINATOR should be "
        "the gRPC coordinator (e.g. host:20408); the REST API is derived automatically"
    )
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "warning: "
    print(f"{prefix}{msg}", file=sys.stderr)


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
