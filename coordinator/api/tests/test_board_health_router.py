"""Tests for board health REST API router."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.auth.store import AuthStore
from app.board_health.runner import HealthCheckRunner
from app.board_health.scheduler import HealthCheckScheduler
from app.board_health.store import BoardHealthStore
from app.catalog import BoardCatalog, BoardEntry
from app.main import app
from app.models import PlaceModel
from app.recorder import Recorder


@pytest.fixture
def health_client(tmp_path, mock_client):
    db_path = str(tmp_path / "test_health.db")
    loop = asyncio.new_event_loop()
    rec = Recorder(db_path)
    loop.run_until_complete(rec.start())
    auth_store = AuthStore(db_path)
    health_store = BoardHealthStore(db_path)
    loop.run_until_complete(health_store.initialize())

    mock_client._places["mini2"] = PlaceModel(
        name="mini2",
        tags={"daughter-board": "adrv9002", "carrier": "zcu102", "boot-strategy": "BootFPGASoC"},
    )
    mock_client._places["tron"] = PlaceModel(
        name="tron",
        tags={
            "daughter-board": "adrv9009zu11eg",
            "carrier": "adrv2crr-fmc",
            "boot-strategy": "BootZynqMPJTAG",
        },
    )

    catalog = BoardCatalog(
        boards={
            "adrv9002": BoardEntry(image="2023_R2_P1"),
            "adrv9009zu11eg": BoardEntry(image="2023_R2_P1"),
        }
    )

    mock_runner = MagicMock(spec=HealthCheckRunner)
    mock_runner.is_running.return_value = False
    mock_runner.cancel_run = AsyncMock(return_value=True)

    mock_scheduler = MagicMock(spec=HealthCheckScheduler)
    mock_scheduler.trigger_schedule = AsyncMock(return_value=[1, 2])

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.coordinator = mock_client
        _app.state.auth_store = auth_store
        _app.state.catalog = catalog
        _app.state.board_health_store = health_store
        _app.state.board_health_runner = mock_runner
        _app.state.board_health_scheduler = mock_scheduler
        _app.state.bootstrap_token = None
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _lifespan

    with TestClient(app) as c:
        loop.run_until_complete(
            auth_store.create_user(username="testuser", password="pw", role="admin")
        )
        c.post("/api/auth/login", json={"username": "testuser", "password": "pw"})
        c.health_store = health_store
        c.mock_runner = mock_runner
        c.mock_scheduler = mock_scheduler
        yield c

    app.router.lifespan_context = original
    loop.run_until_complete(rec.stop())
    loop.close()


def test_get_summary_empty(health_client):
    resp = health_client.get("/api/board-health/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_places"] == 2
    assert data["healthy_count"] == 0
    assert data["untested_count"] == 2
    assert len(data["places"]) == 2

    # Check place tags and catalog default image
    p0 = data["places"][0]
    assert p0["name"] in ("mini2", "tron")
    assert p0["default_image"] == "2023_R2_P1"
    assert p0["last_run"] is None


def test_trigger_run(health_client):
    resp = health_client.post(
        "/api/board-health/runs",
        json={"places": ["mini2"], "image": "2023_R2_P1", "power_down": True},
    )
    assert resp.status_code == 202
    created = resp.json()
    assert len(created) == 1
    assert created[0]["place_name"] == "mini2"
    assert created[0]["status"] == "pending"

    health_client.mock_runner.start_check.assert_called_once()


def test_runs_list_and_detail(health_client):
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete(
        health_client.health_store.create_run(
            place_name="mini2",
            trigger="manual",
            triggered_by="testuser",
        )
    )
    loop.run_until_complete(
        health_client.health_store.finish_run(
            run.id,
            status="passed",
            duration=35.0,
            ip_address="192.168.1.102",
            iiod_reachable=True,
            drivers=["ad9361-phy", "cf-ad9361-lpc"],
            log_output="Boot logs...",
        )
    )
    loop.close()

    # List runs
    resp = health_client.get("/api/board-health/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1
    assert runs[0]["place_name"] == "mini2"
    assert runs[0]["status"] == "passed"
    assert runs[0]["duration"] == 35.0
    assert runs[0]["drivers"] == ["ad9361-phy", "cf-ad9361-lpc"]

    # Get run detail
    detail_resp = health_client.get(f"/api/board-health/runs/{run.id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["log_output"] == "Boot logs..."
    assert detail["iiod_reachable"] is True
    assert detail["drivers"] == ["ad9361-phy", "cf-ad9361-lpc"]


def test_cancel_run(health_client):
    resp = health_client.post("/api/board-health/runs/999/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_schedules_crud(health_client):
    # Create
    resp = health_client.post(
        "/api/board-health/schedules",
        json={
            "name": "Daily Fleet Sanity",
            "description": "Run every morning",
            "cron_expression": "0 6 * * *",
            "places": ["*"],
            "power_down": True,
            "enabled": True,
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    schedule_id = created["id"]
    assert created["name"] == "Daily Fleet Sanity"
    assert created["places"] == ["*"]
    assert created["next_run_at"] is not None

    # List
    list_resp = health_client.get("/api/board-health/schedules")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # Get
    get_resp = health_client.get(f"/api/board-health/schedules/{schedule_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Daily Fleet Sanity"

    # Update
    update_resp = health_client.put(
        f"/api/board-health/schedules/{schedule_id}",
        json={"name": "Weekly Fleet Sanity", "enabled": False},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Weekly Fleet Sanity"
    assert update_resp.json()["enabled"] is False

    # Trigger now
    trigger_resp = health_client.post(f"/api/board-health/schedules/{schedule_id}/trigger")
    assert trigger_resp.status_code == 200
    assert trigger_resp.json()["triggered"] is True

    # Delete
    del_resp = health_client.delete(f"/api/board-health/schedules/{schedule_id}")
    assert del_resp.status_code == 204

    assert health_client.get(f"/api/board-health/schedules/{schedule_id}").status_code == 404
