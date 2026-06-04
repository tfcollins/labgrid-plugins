"""Pure request-matching logic for GET /api/match.

`match_places` is a pure function of (catalog, live places, request) so it
is unit-tested without FastAPI or a coordinator connection. It never
acquires or reserves — it only decides satisfiability and returns how to
provision: the reservation tag-filter, the resolved image, and the boot
strategy. Contention (all matching boards busy) is NOT unsatisfiable here;
that is left to labgrid's reservation queue on the client side.
"""

from __future__ import annotations

from pydantic import BaseModel

from .catalog import BoardCatalog, resolve_image
from .env_gen import resolve_strategy
from .models import PlaceModel


class MatchResult(BaseModel):
    satisfiable: bool
    reservation_filter: dict[str, str] = {}
    image: str | None = None
    strategy: str | None = None
    place: str | None = None  # informational candidate (a free one if any)
    runner: str | None = None  # the candidate place's `runner` tag (CI runner label)
    reason: str | None = None


def _candidates(places: list[PlaceModel], part: str, carrier: str | None) -> list[PlaceModel]:
    out = []
    for p in places:
        if p.tags.get("daughter-board") != part:
            continue
        if carrier is not None and p.tags.get("carrier") != carrier:
            continue
        out.append(p)
    return out


def match_places(
    catalog: BoardCatalog,
    places: list[PlaceModel],
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
) -> MatchResult:
    resolved = catalog.lookup(part)
    if resolved is None:
        return MatchResult(satisfiable=False, reason=f"unknown part: {part!r}")
    # `part` may be an alias (e.g. ad9371); `board` is the canonical key, which
    # equals the place's daughter-board tag. Match and reserve on `board`.
    board, entry = resolved

    if carrier is not None and carrier not in entry.carriers:
        return MatchResult(
            satisfiable=False,
            reason=f"carrier {carrier!r} not valid for part {part!r}",
        )

    candidates = _candidates(places, board, carrier)
    if not candidates:
        where = f"{board!r}" + (f" on {carrier!r}" if carrier else "")
        return MatchResult(satisfiable=False, reason=f"no live place for {where}")

    reservation_filter = {"daughter-board": board}
    if carrier is not None:
        reservation_filter["carrier"] = carrier

    chosen = next((p for p in candidates if p.acquired is None), candidates[0])
    # Strategy comes only from the place's explicit `boot-strategy` tag:
    # we pass an empty resource-class set, so resolve_strategy's shape-based
    # inference (used by env-yaml generation) intentionally does not fire here.
    strategy = resolve_strategy(chosen.tags, set())

    return MatchResult(
        satisfiable=True,
        reservation_filter=reservation_filter,
        image=resolve_image(entry, bootfile),
        strategy=strategy,
        place=chosen.name,
        runner=chosen.tags.get("runner"),
    )
