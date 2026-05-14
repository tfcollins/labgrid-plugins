"""HW-CI v2 — discovery-driven matrix building.

The matrix is built by intersecting:

* live places on the labgrid coordinator (each tagged with carrier,
  daughter-board, boot-strategy — see ``schema.Place``), and
* pytest markers harvested from the caller repo
  (``@pytest.mark.iio_hardware([...])``,
  ``@pytest.mark.iio_carrier([...])``).

Per matrix entry, the workflow renders a labgrid env yaml from the
place's tags so consumer repos don't ship env yamls at all.

This package is the in-Python surface; ``adi_lg_plugins.hw_ci.cli``
wraps it for use from the reusable workflow.
"""

from .schema import (
    KNOWN_STRATEGIES,
    Place,
    PlaceValidationError,
    validate_place,
)
from .intersect import MatrixEntry, MarkerSpec, intersect

__all__ = [
    "KNOWN_STRATEGIES",
    "MarkerSpec",
    "MatrixEntry",
    "Place",
    "PlaceValidationError",
    "intersect",
    "validate_place",
]
