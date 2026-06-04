from fastapi import APIRouter, Query, Request

from ..catalog import BoardCatalog
from ..matching import MatchResult, match_places

router = APIRouter(tags=["catalog"])


def _catalog(request: Request) -> BoardCatalog:
    # Set at startup in main.lifespan. A missing catalog file is non-fatal
    # (load_catalog returns an empty catalog + warning), so we also default
    # to an empty catalog here rather than erroring.
    return getattr(request.app.state, "catalog", BoardCatalog())


def _get_client(request: Request):
    # No getattr fallback (unlike _catalog): a missing coordinator is a hard
    # startup failure, not graceful degradation. Matches app/routers/places.py.
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
    mode: str = Query("uri", description="Provision mode: 'uri' (Kuiper boot) or 'flash' (no-os)"),
) -> MatchResult:
    places = _get_client(request).get_places()
    return match_places(
        _catalog(request), places, part=part, carrier=carrier, bootfile=bootfile, mode=mode
    )
