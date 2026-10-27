"""Tests for BoardHealthStore."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from app.board_health.store import BoardHealthStore


@pytest_asyncio.fixture
async def store():
    with tempfile.NamedTemporaryFile(suffix=".db") as fh:
        db_path = fh.name
    s = BoardHealthStore(db_path)
    await s.initialize()
    yield s
    try:
        Path(db_path).unlink()
    except OSError:
        pass


@pytest.mark.asyncio
async def test_schedule_crud(store: BoardHealthStore):
    s = await store.create_schedule(
        name="Nightly Check",
        description="Run nightly on mini2",
        cron_expression="0 2 * * *",
        places=["mini2"],
        image="2023_R2_P1",
        power_down=True,
    )
    assert s.id is not None
    assert s.name == "Nightly Check"
    assert s.places == ["mini2"]
    assert s.image == "2023_R2_P1"
    assert s.enabled is True
    assert s.next_run_at is not None

    # Get
    fetched = await store.get_schedule(s.id)
    assert fetched is not None
    assert fetched.name == "Nightly Check"

    # List
    all_s = await store.list_schedules()
    assert len(all_s) == 1
    assert all_s[0].id == s.id

    # Update
    updated = await store.update_schedule(s.id, name="Renamed Check", enabled=False)
    assert updated is not None
    assert updated.name == "Renamed Check"
    assert updated.enabled is False
    assert updated.next_run_at is None

    # Delete
    deleted = await store.delete_schedule(s.id)
    assert deleted is True
    assert await store.get_schedule(s.id) is None


@pytest.mark.asyncio
async def test_due_schedules(store: BoardHealthStore):
    s = await store.create_schedule(
        name="Hourly Check",
        cron_expression="* * * * *",
        places=["*"],
    )
    assert s.next_run_at is not None

    # Future time check
    due = await store.get_due_schedules(s.next_run_at + 10)
    assert len(due) == 1
    assert due[0].id == s.id

    # Advance schedule time
    await store.advance_schedule_time(s.id, s.next_run_at + 10)
    s_after = await store.get_schedule(s.id)
    assert s_after.last_run_at is not None
    assert s_after.next_run_at > s.next_run_at


@pytest.mark.asyncio
async def test_runs_lifecycle(store: BoardHealthStore):
    run = await store.create_run(
        place_name="mini2",
        trigger="manual",
        triggered_by="analog",
        image="2023_R2_P1",
    )
    assert run.status == "pending"
    assert run.place_name == "mini2"

    await store.start_run(run.id, boot_strategy="BootFPGASoC")
    running = await store.get_run(run.id)
    assert running.status == "running"
    assert running.boot_strategy == "BootFPGASoC"

    await store.append_run_log(run.id, "Step 1: Powered on\n")
    await store.append_run_log(run.id, "Step 2: Reached shell\n")

    finished = await store.finish_run(
        run.id,
        status="passed",
        duration=42.5,
        ip_address="192.168.1.100",
        iiod_reachable=True,
        drivers=["cf-ad9361-lpc", "ad9361-phy"],
    )
    assert finished.status == "passed"
    assert finished.duration == 42.5
    assert finished.ip_address == "192.168.1.100"
    assert finished.iiod_reachable is True
    assert finished.drivers == ["cf-ad9361-lpc", "ad9361-phy"]
    assert "Step 1" in finished.log_output
    assert "Step 2" in finished.log_output

    # Latest per place
    latest = await store.get_latest_run_per_place()
    assert "mini2" in latest
    assert latest["mini2"].id == run.id
