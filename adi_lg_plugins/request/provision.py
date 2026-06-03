"""Dual-mode board provisioning shared by the pytest fixture and other surfaces.

``provision_or_reuse`` either *reuses* an externally-provided URI (CI: a board
is already booted) or *self-requests* one via the request core (local dev),
releasing it on exit. It is pytest-independent so the reuse-vs-request
branching is unit-tested without pytest.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .core import Lease, request
from .errors import NoBoardSource


@contextmanager
def provision_or_reuse(
    part: str | None,
    carrier: str | None = None,
    *,
    uri: str | None = None,
    coord: str | None = None,
    bootfile: str | None = None,
) -> Iterator[Lease]:
    """Yield a booted board handle.

    - ``uri`` set  -> reuse it (no coordinator contact, release nothing).
    - else ``part`` -> self-request via ``request()`` and release on exit.
    - neither       -> raise :class:`NoBoardSource`.
    """
    if uri:
        # place="" marks an externally-provided board; nothing to release.
        yield Lease(place="", carrier=carrier or "", tags={}, uri=uri)
        return
    if part:
        with request(part=part, carrier=carrier, bootfile=bootfile, coord=coord) as lease:
            yield lease
        return
    raise NoBoardSource("no board configured — set IIO_URI/--adi-uri or --adi-part/ADI_PART")
