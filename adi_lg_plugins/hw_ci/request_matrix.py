"""Build the part-keyed CI matrix for the fresh hardware-request workflow.

Pure of IO: given the parts a test suite wants (harvested from
``iio_hardware`` markers) and a ``satisfiable(part)`` probe, return the matrix
of parts that have a live board (one CI leg each) plus the wanted-but-missing
parts to annotate as skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMatrix:
    parts: list[str]  # available -> one CI leg each
    missing: list[str]  # wanted but no live board -> annotate + skip


def build_request_matrix(
    wanted_parts: Iterable[str],
    satisfiable: Callable[[str], bool],
) -> RequestMatrix:
    parts: list[str] = []
    missing: list[str] = []
    for part in sorted(set(wanted_parts)):
        (parts if satisfiable(part) else missing).append(part)
    return RequestMatrix(parts=parts, missing=missing)
