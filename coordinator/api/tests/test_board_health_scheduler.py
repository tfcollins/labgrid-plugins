"""Tests for HealthCheckScheduler."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from app.board_health.runner import HealthCheckRunner
from app.board_health.scheduler import HealthCheckScheduler
from app.board_health.store import BoardHealthStore
from app.models import PlaceModel


@pytest_asyncio.fixture
async def scheduler_env():
    with tempfile.NamedTemporaryFile(suffix=".db") as fh:
        db_path = fh.name
    store = BoardHealthStore(db_path)
    await store.initialize()

    mock_client = MagicMock()
    mock_client.get_places.return_value = [
        PlaceModel(name="mini2"),
        PlaceModel(name="tron"),
    ]

    mock_runner = MagicMock(spec=HealthCheckRunner)
    mock_runner.start_check = MagicMock()

    scheduler = HealthCheckScheduler(
        store=store,
        runner=mock_runner,
        coordinator_client=mock_client,
        check_interval=0.1,
    )

    yield store, scheduler, mock_runner, mock_client

    await scheduler.stop()
    try:
        Path(db_path).unlink()
    except OSError:
        pass


@pytest.mark.asyncio
async def test_scheduler_trigger_all_places(scheduler_env):
    store, scheduler, mock_runner, mock_client = scheduler_env

    sched = await store.create_schedule(
        name="All Boards Check",
        cron_expression="* * * * *",
        places=["*"],
        image="2023_R2_P1",
    )

    run_ids = await scheduler.trigger_schedule(sched.id)
    assert len(run_ids) == 2
    assert mock_runner.start_check.call_count == 2

    # Check runs in store
    runs = await store.list_runs()
    assert len(runs) == 2
    place_names = {r.place_name for r in runs}
    assert place_names == {"mini2", "tron"}
    assert runs[0].trigger == "scheduled"
    assert runs[0].triggered_by == "All Boards Check"


@pytest.mark.asyncio
async def test_scheduler_trigger_specific_places(scheduler_env):
    store, scheduler, mock_runner, mock_client = scheduler_env

    sched = await store.create_schedule(
        name="Single Board Check",
        cron_expression="* * * * *",
        places=["mini2"],
    )

    run_ids = await scheduler.trigger_schedule(sched.id)
    assert len(run_ids) == 1
    assert mock_runner.start_check.call_count == 1

    runs = await store.list_runs()
    assert len(runs) == 1
    assert runs[0].place_name == "mini2"
