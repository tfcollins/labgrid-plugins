"""Intersect harvested pytest markers with live coordinator places.

Inputs:

* ``markers`` — for each test node id, the set of daughter-board names
  the test wants (``iio_hardware`` marker) and the optional set of
  carriers it narrows to (``iio_carrier``).
* ``places``  — :class:`~adi_lg_plugins.hw_ci.schema.Place` list from
  the coordinator, already validated.

Output: a list of :class:`MatrixEntry`, one per (place, daughter)
pairing that has at least one matching test. The entry carries:

* the labgrid place to acquire
* a pytest ``-m`` expression that selects exactly the tests intended
  for this entry
* the list of pytest node ids (for explicit invocation when the caller
  prefers that over marker-only filtering)
* the boot-strategy tag value (so the workflow knows which env yaml
  template to render)

This module is pure; no I/O, no subprocess.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from .schema import Place


@dataclass(frozen=True)
class MarkerSpec:
    """The HW-CI markers on a single pytest test."""

    iio_hardware: frozenset[str]
    iio_carrier: frozenset[str] = frozenset()

    @classmethod
    def of(
        cls,
        iio_hardware: Iterable[str],
        iio_carrier: Iterable[str] = (),
    ) -> MarkerSpec:
        return cls(
            iio_hardware=frozenset(iio_hardware),
            iio_carrier=frozenset(iio_carrier),
        )


@dataclass(frozen=True)
class MatrixEntry:
    """One slot in the discovery-driven matrix."""

    place: str
    carrier: str
    daughter_board: str
    boot_strategy: str
    marker_filter: str  # pytest -m expression
    tests: tuple[str, ...]  # node ids, deterministically sorted
    hdl_config: str | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def as_matrix_dict(self) -> dict:
        """JSON-serializable form for GHA matrix include."""
        return {
            "place": self.place,
            "carrier": self.carrier,
            "daughter_board": self.daughter_board,
            "boot_strategy": self.boot_strategy,
            "marker_filter": self.marker_filter,
            "tests": list(self.tests),
            "hdl_config": self.hdl_config or "",
            **{f"x_{k}": v for k, v in sorted(self.extra.items())},
        }


def _test_matches_place(spec: MarkerSpec, place: Place) -> bool:
    """A test runs on a place iff:

    * the test's ``iio_hardware`` set contains the place's daughter-board, AND
    * the test's ``iio_carrier`` set is empty OR contains the place's carrier.
    """
    if place.daughter_board not in spec.iio_hardware:
        return False
    if spec.iio_carrier and place.carrier not in spec.iio_carrier:
        return False
    return True


def intersect(
    markers: Mapping[str, MarkerSpec],
    places: Iterable[Place],
    *,
    skip_acquired: bool = True,
) -> list[MatrixEntry]:
    """Build the matrix from harvested markers + live places.

    Returns one entry per (place, daughter-board) for which at least
    one test wants to run. Tests are grouped per place into a single
    ``-m`` expression so each shard runs in a single pytest invocation.

    Acquired places are skipped by default; set ``skip_acquired=False``
    to include them (useful for dry-run / what-if invocations).
    """
    # Group test ids by (place_name) — multiple tests can share a slot.
    per_place: dict[str, list[str]] = {}
    place_by_name: dict[str, Place] = {}

    for place in places:
        if skip_acquired and place.is_acquired:
            continue
        place_by_name[place.name] = place

    for test_id, spec in markers.items():
        for place_name, place in place_by_name.items():
            if _test_matches_place(spec, place):
                per_place.setdefault(place_name, []).append(test_id)

    entries: list[MatrixEntry] = []
    for place_name, tests in per_place.items():
        place = place_by_name[place_name]
        sorted_tests = tuple(sorted(tests))
        marker_filter = f"iio_hardware and {place.daughter_board}"
        # If the place has an hdl-config tag, narrow further so any
        # test that marked iio_hdl_config gets honored. The marker
        # name is reserved here so consumers can adopt it later
        # without a schema change.
        entries.append(
            MatrixEntry(
                place=place.name,
                carrier=place.carrier,
                daughter_board=place.daughter_board,
                boot_strategy=place.boot_strategy,
                marker_filter=marker_filter,
                tests=sorted_tests,
                hdl_config=place.hdl_config,
                extra=dict(place.extra_tags),
            )
        )
    entries.sort(key=lambda e: (e.daughter_board, e.place))
    return entries
