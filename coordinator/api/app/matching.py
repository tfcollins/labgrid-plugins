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

from .catalog import BoardCatalog, FlashConfig, resolve_image
from .env_gen import resolve_strategy
from .models import PlaceModel


class MatchResult(BaseModel):
    satisfiable: bool
    reservation_filter: dict[str, str] = {}
    image: str | None = None
    strategy: str | None = None
    place: str | None = None  # informational candidate (a free one if any)
    runner: str | None = None  # the candidate place's `runner` tag (CI runner label)
    flash: FlashConfig | None = None  # no-os flash metadata (mode="flash" only)
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
    mode: str = "uri",
) -> MatchResult:
    resolved = catalog.lookup(part)
    if resolved is None:
        return MatchResult(satisfiable=False, reason=f"unknown part: {part!r}")
    # `part` may be an alias (e.g. ad9371); `board` is the canonical key, which
    # equals the place's daughter-board tag. Match and reserve on `board`.
    board, entry = resolved

    # mode="flash" runs no-os firmware on the board via a JTAG flash strategy
    # instead of booting Kuiper; only boards with a `flash` block support it.
    if mode == "flash" and entry.flash is None:
        return MatchResult(
            satisfiable=False,
            reason=f"part {part!r} has no flash (no-os) support",
        )

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
    if mode == "flash":
        # The flash strategy comes from the catalog and OVERRIDES the place's
        # boot-strategy tag (the same board serves Kuiper or no-os). The Kuiper
        # `image` is still returned — build-noos sources the board's .xsa from
        # that Kuiper release; the firmware itself is built + passed by the client.
        strategy = entry.flash.strategy
        image = entry.image
        flash = entry.flash
    else:
        # Strategy comes only from the place's explicit `boot-strategy` tag:
        # we pass an empty resource-class set, so resolve_strategy's shape-based
        # inference (used by env-yaml generation) intentionally does not fire here.
        strategy = resolve_strategy(chosen.tags, set())
        image = resolve_image(entry, bootfile)
        flash = None

    return MatchResult(
        satisfiable=True,
        reservation_filter=reservation_filter,
        image=image,
        strategy=strategy,
        place=chosen.name,
        runner=chosen.tags.get("runner"),
        flash=flash,
    )
