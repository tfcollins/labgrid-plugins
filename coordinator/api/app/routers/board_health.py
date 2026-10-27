"""Board health check REST API router."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..auth.dependencies import current_user
from ..auth.store import User
from ..board_health.runner import HealthCheckRunner
from ..board_health.scheduler import HealthCheckScheduler
from ..board_health.store import BoardHealthStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["board-health"], prefix="/board-health")


# --- Request / Response Models ---


class TriggerRunRequest(BaseModel):
    places: list[str] = Field(..., min_length=1, description="List of place names to check")
    image: str | None = Field(default=None, description="Golden boot image version override")
    power_down: bool = Field(default=True, description="Power off board after check completes")


class CreateScheduleRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    cron_expression: str = Field(..., min_length=1, max_length=64)
    places: list[str] = Field(default_factory=lambda: ["*"])
    image: str | None = Field(default=None, max_length=128)
    power_down: bool = True
    enabled: bool = True


class UpdateScheduleRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    cron_expression: str | None = Field(default=None, max_length=64)
    places: list[str] | None = None
    image: str | None = Field(default=None, max_length=128)
    power_down: bool | None = None
    enabled: bool | None = None


# --- Helper accessors ---


def _store(request: Request) -> BoardHealthStore:
    return request.app.state.board_health_store


def _runner(request: Request) -> HealthCheckRunner:
    return request.app.state.board_health_runner


def _scheduler(request: Request) -> HealthCheckScheduler:
    return request.app.state.board_health_scheduler


# --- Endpoints ---


@router.get("/summary")
async def get_summary(request: Request, _user: User = Depends(current_user)):
    """Return summary KPI metrics and status for all deployed boards."""
    store = _store(request)
    client = request.app.state.coordinator
    catalog = getattr(request.app.state, "catalog", None)

    try:
        places = client.get_places()
    except Exception as e:
        logger.warning("Could not list places from coordinator: %s", e)
        places = []

    latest_runs = await store.get_latest_run_per_place()

    healthy_count = 0
    failing_count = 0
    untested_count = 0
    running_count = 0

    places_summary = []
    for p in places:
        daughter_board = p.tags.get("daughter-board")
        carrier = p.tags.get("carrier")
        boot_strategy = p.tags.get("boot-strategy")

        default_image = None
        if catalog and daughter_board:
            lookup = catalog.lookup(daughter_board)
            if lookup:
                default_image = lookup[1].image

        last_run = latest_runs.get(p.name)
        if last_run:
            if last_run.status == "passed":
                healthy_count += 1
            elif last_run.status in ("failed", "busy"):
                failing_count += 1
            elif last_run.status == "running":
                running_count += 1
            else:
                untested_count += 1

            last_run_dict = {
                "id": last_run.id,
                "status": last_run.status,
                "started_at": last_run.started_at,
                "finished_at": last_run.finished_at,
                "duration": last_run.duration,
                "boot_strategy": last_run.boot_strategy or boot_strategy,
                "image": last_run.image or default_image,
                "ip_address": last_run.ip_address,
                "iiod_reachable": last_run.iiod_reachable,
                "error_message": last_run.error_message,
                "trigger": last_run.trigger,
                "triggered_by": last_run.triggered_by,
            }
        else:
            untested_count += 1
            last_run_dict = None

        places_summary.append(
            {
                "name": p.name,
                "daughter_board": daughter_board,
                "carrier": carrier,
                "boot_strategy": boot_strategy,
                "acquired": p.acquired,
                "default_image": default_image,
                "last_run": last_run_dict,
            }
        )

    return {
        "total_places": len(places),
        "healthy_count": healthy_count,
        "failing_count": failing_count,
        "untested_count": untested_count,
        "running_count": running_count,
        "places": places_summary,
    }


@router.get("/runs")
async def list_runs(
    request: Request,
    place: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _user: User = Depends(current_user),
):
    """List historical health check runs with pagination and filtering."""
    store = _store(request)
    runs = await store.list_runs(place_name=place, status=status, limit=limit, offset=offset)
    return [
        {
            "id": r.id,
            "place_name": r.place_name,
            "status": r.status,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "duration": r.duration,
            "boot_strategy": r.boot_strategy,
            "image": r.image,
            "ip_address": r.ip_address,
            "iiod_reachable": r.iiod_reachable,
            "error_message": r.error_message,
            "trigger": r.trigger,
            "triggered_by": r.triggered_by,
            "schedule_id": r.schedule_id,
        }
        for r in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: int, request: Request, _user: User = Depends(current_user)):
    """Get single health check run including full execution log."""
    store = _store(request)
    run = await store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return {
        "id": run.id,
        "place_name": run.place_name,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration": run.duration,
        "boot_strategy": run.boot_strategy,
        "image": run.image,
        "ip_address": run.ip_address,
        "iiod_reachable": run.iiod_reachable,
        "error_message": run.error_message,
        "log_output": run.log_output,
        "trigger": run.trigger,
        "triggered_by": run.triggered_by,
        "schedule_id": run.schedule_id,
    }


@router.post("/runs", status_code=202)
async def trigger_runs(
    body: TriggerRunRequest,
    request: Request,
    user: User = Depends(current_user),
):
    """Trigger on-demand health check runs for specified places."""
    store = _store(request)
    runner = _runner(request)
    created_runs = []

    for place_name in body.places:
        run = await store.create_run(
            place_name=place_name,
            trigger="manual",
            triggered_by=user.username,
            image=body.image,
        )
        runner.start_check(
            run_id=run.id,
            place_name=place_name,
            image=body.image,
            power_down=body.power_down,
        )
        created_runs.append(
            {
                "id": run.id,
                "place_name": run.place_name,
                "status": run.status,
                "started_at": run.started_at,
            }
        )

    return created_runs


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int, request: Request, _user: User = Depends(current_user)):
    """Cancel an in-progress health check run."""
    runner = _runner(request)
    cancelled = await runner.cancel_run(run_id)
    if not cancelled:
        # Check if already finished
        store = _store(request)
        run = await store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        if run.status != "running":
            return {"status": run.status, "message": "Run was not active"}

    return {"status": "cancelled", "run_id": run_id}


# --- Schedules Endpoints ---


@router.get("/schedules")
async def list_schedules(request: Request, _user: User = Depends(current_user)):
    """List recurring health check schedules."""
    store = _store(request)
    schedules = await store.list_schedules()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "cron_expression": s.cron_expression,
            "places": s.places,
            "image": s.image,
            "power_down": s.power_down,
            "enabled": s.enabled,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "last_run_at": s.last_run_at,
            "next_run_at": s.next_run_at,
        }
        for s in schedules
    ]


@router.post("/schedules", status_code=201)
async def create_schedule(
    body: CreateScheduleRequest,
    request: Request,
    _user: User = Depends(current_user),
):
    """Create a new recurring health check schedule."""
    store = _store(request)
    schedule = await store.create_schedule(
        name=body.name,
        description=body.description,
        cron_expression=body.cron_expression,
        places=body.places,
        image=body.image,
        power_down=body.power_down,
        enabled=body.enabled,
    )
    return {
        "id": schedule.id,
        "name": schedule.name,
        "description": schedule.description,
        "cron_expression": schedule.cron_expression,
        "places": schedule.places,
        "image": schedule.image,
        "power_down": schedule.power_down,
        "enabled": schedule.enabled,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
        "last_run_at": schedule.last_run_at,
        "next_run_at": schedule.next_run_at,
    }


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: int, request: Request, _user: User = Depends(current_user)):
    """Get schedule by ID."""
    store = _store(request)
    s = await store.get_schedule(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "cron_expression": s.cron_expression,
        "places": s.places,
        "image": s.image,
        "power_down": s.power_down,
        "enabled": s.enabled,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "last_run_at": s.last_run_at,
        "next_run_at": s.next_run_at,
    }


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    body: UpdateScheduleRequest,
    request: Request,
    _user: User = Depends(current_user),
):
    """Update recurring health check schedule."""
    store = _store(request)
    s = await store.update_schedule(
        schedule_id,
        name=body.name,
        description=body.description,
        cron_expression=body.cron_expression,
        places=body.places,
        image=body.image,
        power_down=body.power_down,
        enabled=body.enabled,
    )
    if s is None:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "cron_expression": s.cron_expression,
        "places": s.places,
        "image": s.image,
        "power_down": s.power_down,
        "enabled": s.enabled,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "last_run_at": s.last_run_at,
        "next_run_at": s.next_run_at,
    }


@router.delete("/schedules/{schedule_id}", status_code=204)
async def delete_schedule(schedule_id: int, request: Request, _user: User = Depends(current_user)):
    """Delete a schedule."""
    store = _store(request)
    deleted = await store.delete_schedule(schedule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")


@router.post("/schedules/{schedule_id}/trigger")
async def trigger_schedule_now(
    schedule_id: int,
    request: Request,
    _user: User = Depends(current_user),
):
    """Trigger immediate execution of a scheduled check."""
    scheduler = _scheduler(request)
    run_ids = await scheduler.trigger_schedule(schedule_id)
    return {"triggered": True, "schedule_id": schedule_id, "run_ids": run_ids}
