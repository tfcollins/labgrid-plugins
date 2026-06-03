"""Low-config hardware request layer (Phase 1: uri mode).

Public API:
    from adi_lg_plugins.request import request
    with request(part="ad9361") as board:
        sdr = adi.ad9361(uri=board.uri)

See docs/superpowers/specs/2026-06-02-low-config-hardware-request-design.md.
"""

from .core import Lease, request
from .errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)

__all__ = [
    "request",
    "Lease",
    "RequestError",
    "NoMatchingBoard",
    "BoardUnavailable",
    "ProvisionError",
]
