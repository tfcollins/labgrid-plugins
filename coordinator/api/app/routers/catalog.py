from fastapi import APIRouter, Request

from ..catalog import load_catalog, match_places
from ..config import settings
from ..models import CatalogModel, MatchResponse

router = APIRouter(tags=["catalog"])


def _get_client(request: Request):
    return request.app.state.coordinator


def _load() -> object:
    return load_catalog(settings.board_catalog_path)


@router.get("/catalog", response_model=CatalogModel)
async def get_catalog():
    cat = _load()
    return {
        "channels": cat.channels,
        "boards": {
            part: {
                "image_channel": b.image_channel,
                "carriers": {cn: {"matlab_board": c.matlab_board} for cn, c in b.carriers.items()},
            }
            for part, b in cat.boards.items()
        },
    }


@router.get("/match", response_model=MatchResponse)
async def match(
    request: Request,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
):
    cat = _load()
    places = _get_client(request).get_places()
    # Normalise PlaceModel objects or dicts to plain dicts.
    norm = [p if isinstance(p, dict) else p.model_dump() for p in places]
    data = match_places(cat, norm, part=part, carrier=carrier, bootfile=bootfile)
    return {
        "satisfiable": data.satisfiable,
        "reason": data.reason,
        "reservation_filter": data.reservation_filter,
        "version": data.version,
        "matlab_boards": data.matlab_boards,
        "candidates": [
            {"place": c.place, "carrier": c.carrier, "acquired": c.acquired}
            for c in data.candidates
        ],
    }
