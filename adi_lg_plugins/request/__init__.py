"""Low-config hardware request layer (uri mode).

Public API::

    from adi_lg_plugins.request import request

    with request(part="adrv9002") as board:
        sdr = adi.adrv9002(uri=board.uri)

See docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md.
"""

from .core import Lease, request
from .errors import (
    BoardUnavailable,
    NoBoardSource,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)
from .provision import provision_or_reuse

__all__ = [
    "request",
    "Lease",
    "provision_or_reuse",
    "RequestError",
    "NoMatchingBoard",
    "BoardUnavailable",
    "ProvisionError",
    "NoBoardSource",
]
