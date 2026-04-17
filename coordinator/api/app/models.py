from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ResourceMatchModel(BaseModel):
    exporter: str
    group: str
    cls: str
    name: str | None = None
    rename: str | None = None


class PlaceModel(BaseModel):
    name: str
    aliases: list[str] = []
    comment: str = ""
    tags: dict[str, str] = {}
    matches: list[ResourceMatchModel] = []
    acquired: str | None = None
    acquired_resources: list[list[str]] = []
    allowed: list[str] = []
    created: float = 0.0
    changed: float = 0.0
    reservation: str | None = None
    acquired_username: str | None = None


class ResourceModel(BaseModel):
    exporter: str
    group: str
    cls: str
    name: str
    params: dict[str, Any] = {}
    acquired: str | None = None
    avail: bool = False


class ExporterModel(BaseModel):
    name: str
    groups: dict[str, list[ResourceModel]] = {}


class ReservationFilterModel(BaseModel):
    filter: dict[str, str] = {}


class ReservationModel(BaseModel):
    owner: str
    token: str
    state: str
    prio: float = 0.0
    filters: dict[str, ReservationFilterModel] = {}
    allocations: dict[str, str] = {}
    created: float = 0.0
    timeout: float = 0.0


class CreatePlaceRequest(BaseModel):
    name: str


class AddMatchRequest(BaseModel):
    pattern: str
    rename: str | None = None


class SetTagsRequest(BaseModel):
    tags: dict[str, str]


class SetCommentRequest(BaseModel):
    comment: str


class CreateReservationRequest(BaseModel):
    filters: dict[str, dict[str, str]]
    prio: float = 0.0


class EventModel(BaseModel):
    id: int
    timestamp: float
    event_type: str
    place_name: str | None = None
    resource_key: str | None = None
    user: str | None = None
    details: str | None = None


class EventsResponse(BaseModel):
    events: list[EventModel]
    total: int


class PlaceStatsModel(BaseModel):
    place_name: str
    total_sessions: int
    total_acquired_seconds: float
    utilization_percent: float
    last_acquired_by: str | None = None


class PlaceSessionModel(BaseModel):
    user: str
    acquired_at: float
    released_at: float | None = None
    duration_seconds: float


class ResourceStatsModel(BaseModel):
    resource_key: str
    uptime_percent: float
    total_online_seconds: float
    total_offline_seconds: float
    last_changed: float | None = None


class ExporterStatsModel(BaseModel):
    exporter: str
    resource_count: int
    avg_uptime_percent: float


class OverviewStatsModel(BaseModel):
    total_events_24h: int
    avg_acquisition_duration_hours: float
    busiest_hour: int
    most_used_place: str | None = None
    avg_uptime_percent: float
