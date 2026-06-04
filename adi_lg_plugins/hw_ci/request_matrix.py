"""Build the part-keyed CI matrix for the fresh hardware-request workflow.

Pure of IO: given the parts a test suite wants (harvested from
``iio_hardware`` markers) and a ``probe`` that resolves a part to a live
board, return the matrix of parts that have one (one CI leg each, carrying
the board's co-located runner label) plus the wanted-but-missing parts to
annotate as skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol


class _Match(Protocol):
    """The slice of a /api/match result the matrix builder needs."""

    satisfiable: bool
    runner: str | None


@dataclass
class MatrixLeg:
    part: str
    runner: str | None = None  # self-hosted runner label the board is wired to


@dataclass
class RequestMatrix:
    parts: list[MatrixLeg]  # available -> one CI leg each
    missing: list[str]  # wanted but no live board -> annotate + skip


def build_request_matrix(
    wanted_parts: Iterable[str],
    probe: Callable[[str], _Match | None],
) -> RequestMatrix:
    """Split wanted parts into runnable legs and missing parts.

    ``probe(part)`` returns a match result (truthy ``.satisfiable`` plus an
    optional ``.runner`` label) for a live board, or ``None``/an unsatisfiable
    result when no board matches (including on a probe error).
    """
    parts: list[MatrixLeg] = []
    missing: list[str] = []
    for part in sorted(set(wanted_parts)):
        res = probe(part)
        if res is not None and getattr(res, "satisfiable", False):
            parts.append(MatrixLeg(part=part, runner=getattr(res, "runner", None)))
        else:
            missing.append(part)
    return RequestMatrix(parts=parts, missing=missing)
