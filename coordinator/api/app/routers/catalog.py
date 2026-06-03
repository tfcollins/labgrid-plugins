from fastapi import APIRouter, Query, Request

from ..catalog import BoardCatalog
from ..matching import MatchResult, match_places

router = APIRouter(tags=["catalog"])


def _catalog(request: Request) -> BoardCatalog:
    # Set at startup in main.lifespan; default-empty if loading failed.
    return getattr(request.app.state, "catalog", BoardCatalog())


def _client(request: Request):
    return request.app.state.coordinator


@router.get("/catalog", response_model=BoardCatalog)
async def get_catalog(request: Request) -> BoardCatalog:
    return _catalog(request)


@router.get("/match", response_model=MatchResult)
async def get_match(
    request: Request,
    part: str = Query(..., description="Part / daughter-board, e.g. adrv9002"),
    carrier: str | None = Query(None, description="Optional FPGA carrier, e.g. zcu102"),
    bootfile: str | None = Query(None, description="Optional image/version pin"),
) -> MatchResult:
    places = _client(request).get_places()
    return match_places(_catalog(request), places, part=part, carrier=carrier, bootfile=bootfile)
