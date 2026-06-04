"""no-os hardware-CI discovery: map no-os projects to live flash-capable boards.

Unlike pyadi-iio (which gates on ``@pytest.mark.iio_hardware`` markers harvested
from test files), no-os has no pytest markers. Instead a small **manifest**
(committed in no-os, e.g. ``tools/hw_ci/projects.yaml``) declares which
``projects/<noos_project>`` builds which ``part`` on which ``carriers``. The
preflight intersects that with the coordinator's live flash-capable boards
(``GET /api/match?...&mode=flash``) to produce one CI leg per buildable+live
project; the rest are annotated as skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import yaml


@dataclass
class NoOSProject:
    noos_project: str  # projects/<noos_project>
    part: str  # coordinator part to request (may be a catalog alias, e.g. ad9371)
    carriers: list[str]  # FPGA carriers this project supports, in preference order


@dataclass
class NoOSLeg:
    part: str
    noos_project: str
    carrier: str
    runner: str | None = None  # self-hosted runner co-located with the board


def load_noos_manifest(path: str) -> list[NoOSProject]:
    """Parse a no-os hw-CI manifest YAML into ``NoOSProject`` entries."""
    data = yaml.safe_load(open(path, encoding="utf-8").read()) or {}
    out: list[NoOSProject] = []
    for entry in data.get("projects", []):
        out.append(
            NoOSProject(
                noos_project=entry["noos_project"],
                part=entry["part"],
                carriers=list(entry.get("carriers", [])),
            )
        )
    return out


def build_noos_matrix(
    projects: list[NoOSProject],
    probe: Callable[[str, str], object | None],
) -> tuple[list[NoOSLeg], list[str]]:
    """Split projects into runnable legs and missing (no live board) projects.

    ``probe(part, carrier)`` returns a match result (truthy ``.satisfiable`` +
    optional ``.runner``) for a live flash-capable board, or a falsy/None result
    otherwise. The first satisfiable carrier (in manifest order) wins.
    """
    legs: list[NoOSLeg] = []
    missing: list[str] = []
    for proj in projects:
        chosen: tuple[str, object] | None = None
        for carrier in proj.carriers:
            res = probe(proj.part, carrier)
            if res is not None and getattr(res, "satisfiable", False):
                chosen = (carrier, res)
                break
        if chosen is None:
            missing.append(proj.noos_project)
            continue
        carrier, res = chosen
        legs.append(
            NoOSLeg(
                part=proj.part,
                noos_project=proj.noos_project,
                carrier=carrier,
                runner=getattr(res, "runner", None),
            )
        )
    return legs, missing
