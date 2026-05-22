"""Intersect live coordinator places with a MATLAB board map.

The MATLAB analogue of :mod:`adi_lg_plugins.hw_ci.intersect`. Where the
pytest path pairs ``@pytest.mark.iio_hardware`` markers with places, the
MATLAB path pairs a consumer-supplied board map (see
:mod:`~adi_lg_plugins.matlab_ci.board_map`) with places: a place is
testable iff the board map knows a MATLAB board reference name for its
``(carrier, daughter-board, hdl-config)`` tags.

Output is a list of :class:`MatlabMatrixEntry`, one per testable place,
serialisable into a GitHub Actions ``matrix.include`` array. Each entry
pins to a ``hw-<place>`` self-hosted runner (the same routing convention
``hw-matrix.yml`` uses).

This module is pure — no I/O, no subprocess. The caller fetches places
via :func:`adi_lg_plugins.hw_ci.coordinator.list_live_places`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from adi_lg_plugins.hw_ci.schema import Place

from .board_map import BoardMap


@dataclass(frozen=True)
class MatlabMatrixEntry:
    """One slot in the MATLAB HW-CI matrix."""

    place: str
    matlab_board: str
    carrier: str
    daughter_board: str
    boot_strategy: str
    hdl_config: str | None = None

    @property
    def runner_label(self) -> str:
        """Self-hosted runner label the shard pins to (``hw-<place>``)."""
        return f"hw-{self.place}"

    def as_matrix_dict(self) -> dict:
        """JSON-serializable form for a GHA ``matrix.include`` entry."""
        return {
            "place": self.place,
            "matlab_board": self.matlab_board,
            "carrier": self.carrier,
            "daughter_board": self.daughter_board,
            "boot_strategy": self.boot_strategy,
            "hdl_config": self.hdl_config or "",
            "runner_label": self.runner_label,
        }


def discover(
    board_map: BoardMap,
    places: Iterable[Place],
    *,
    skip_acquired: bool = True,
) -> list[MatlabMatrixEntry]:
    """Build the MATLAB matrix from a board map + live places.

    One entry per place whose tags resolve to a MATLAB board name.
    Places not in the board map are silently skipped (the toolbox has no
    test entry point for that hardware). Acquired places are skipped by
    default; pass ``skip_acquired=False`` for dry-run / what-if listing.
    """
    entries: list[MatlabMatrixEntry] = []
    for place in places:
        if skip_acquired and place.is_acquired:
            continue
        matlab_board = board_map.lookup(place)
        if matlab_board is None:
            continue
        entries.append(
            MatlabMatrixEntry(
                place=place.name,
                matlab_board=matlab_board,
                carrier=place.carrier,
                daughter_board=place.daughter_board,
                boot_strategy=place.boot_strategy,
                hdl_config=place.hdl_config,
            )
        )
    entries.sort(key=lambda e: (e.matlab_board, e.place))
    return entries
