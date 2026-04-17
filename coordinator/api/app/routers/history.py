from fastapi import APIRouter, Request

from ..models import (
    EventModel,
    EventsResponse,
    ExporterStatsModel,
    OverviewStatsModel,
    PlaceSessionModel,
    PlaceStatsModel,
    ResourceStatsModel,
)

router = APIRouter(tags=["history"])


@router.get("/events", response_model=EventsResponse)
async def get_events(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    event_type: str | None = None,
    place_name: str | None = None,
    since: float | None = None,
    until: float | None = None,
):
    recorder = request.app.state.recorder
    events, total = await recorder.get_events(
        limit=limit,
        offset=offset,
        event_type=event_type,
        place_name=place_name,
        since=since,
        until=until,
    )
    return EventsResponse(events=[EventModel(**e) for e in events], total=total)


@router.get("/stats/places", response_model=list[PlaceStatsModel])
async def get_place_stats(request: Request, days: int = 30):
    return await request.app.state.recorder.get_place_stats(days)


@router.get("/stats/places/{name}/sessions", response_model=list[PlaceSessionModel])
async def get_place_sessions(name: str, request: Request):
    return await request.app.state.recorder.get_place_sessions(name)


@router.get("/stats/resources", response_model=list[ResourceStatsModel])
async def get_resource_stats(request: Request, days: int = 30):
    return await request.app.state.recorder.get_resource_stats(days)


@router.get("/stats/exporters", response_model=list[ExporterStatsModel])
async def get_exporter_stats(request: Request, days: int = 30):
    return await request.app.state.recorder.get_exporter_stats(days)


@router.get("/stats/overview", response_model=OverviewStatsModel)
async def get_overview(request: Request):
    return await request.app.state.recorder.get_overview()
