"""no-os hardware-CI discovery: map no-os projects to live flash-capable boards.

Unlike pyadi-iio (which gates on ``@pytest.mark.iio_hardware`` markers harvested
from test files), no-os has no pytest markers. Instead a small **manifest**
(committed in no-os, e.g. ``tools/hw_ci/projects.yaml``) declares which
``projects/<noos_project>`` builds which ``part`` on which ``carriers``, plus
optional ``validate_banner`` (on-target serial success marker, default
``"Successfully initialized"``) and ``build_vars`` (extra ``make`` variables).
The preflight intersects that with the coordinator's live flash-capable boards
(``GET /api/match?...&mode=flash``) to produce one CI leg per buildable+live
project; the rest are annotated as skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field

DEFAULT_VALIDATE_BANNER = "Successfully initialized"


class NoOSProject(BaseModel):
    noos_project: str  # projects/<noos_project>
    part: str  # coordinator part to request (may be a catalog alias, e.g. ad9371)
    carriers: list[str] = Field(min_length=1)  # FPGA carriers, preference order; >=1 required
    validate_banner: str = DEFAULT_VALIDATE_BANNER  # on-target serial success marker
    build_vars: dict[str, str] = {}  # extra `make` variables (K=V)

    model_config = {"frozen": True}

    def __eq__(self, other: object) -> bool:  # dataclass-style equality for tests
        if not isinstance(other, NoOSProject):
            return NotImplemented
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        return hash((self.noos_project, self.part, tuple(self.carriers)))


@dataclass
class NoOSLeg:
    part: str
    noos_project: str
    carrier: str
    runner: str | None = None  # self-hosted runner co-located with the board
    board: str | None = None  # canonical daughter-board (.xsa key), e.g. adrv9371
    release: str | None = None  # Kuiper release the board boots (the .xsa source)
    validate_banner: str = DEFAULT_VALIDATE_BANNER
    build_vars: dict[str, str] = field(default_factory=dict)


def load_noos_manifest(path: str) -> list[NoOSProject]:
    """Parse + validate a no-os hw-CI manifest YAML into ``NoOSProject`` entries.

    Raises ``pydantic.ValidationError`` (a ``ValueError``) on a malformed entry
    (e.g. a missing ``noos_project``/``part``)."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f.read()) or {}
    return [NoOSProject.model_validate(entry) for entry in data.get("projects", [])]


def build_noos_matrix(
    projects: list[NoOSProject],
    probe: Callable[[str, str], object | None],
) -> tuple[list[NoOSLeg], list[str]]:
    """Split projects into runnable legs and missing (no live board) projects.

    ``probe(part, carrier)`` returns a match result (truthy ``.satisfiable`` plus
    ``.runner``, ``.image``, ``.reservation_filter``) for a live flash-capable
    board, or a falsy/None result otherwise. The first satisfiable carrier (in
    manifest order) wins. The leg carries the canonical daughter-board (from
    ``reservation_filter``) + the Kuiper ``image`` release so the build can fetch
    the board's ``.xsa``."""
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
        reservation_filter = getattr(res, "reservation_filter", None) or {}
        legs.append(
            NoOSLeg(
                part=proj.part,
                noos_project=proj.noos_project,
                carrier=carrier,
                runner=getattr(res, "runner", None),
                board=reservation_filter.get("daughter-board"),
                release=getattr(res, "image", None),
                validate_banner=proj.validate_banner,
                build_vars=dict(proj.build_vars),
            )
        )
    return legs, missing
