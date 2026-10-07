from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.store import AuthStore
from app.config import settings
from app.deployments.store import DeploymentStore
from app.recorder import Recorder
from app.routers.deployments import router

TOKEN = "test-deployment-token-with-sufficient-entropy"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def deployment_client(tmp_path):
    db = str(tmp_path / "coordinator.db")
    loop = asyncio.new_event_loop()
    recorder = Recorder(db)
    loop.run_until_complete(recorder.start())
    deployment_store = DeploymentStore(db)
    loop.run_until_complete(deployment_store.initialize())
    auth_store = AuthStore(db)

    app = FastAPI()
    app.state.deployment_store = deployment_store
    app.state.auth_store = auth_store
    app.include_router(router, prefix="/api")

    original_token = settings.deployment_token
    settings.deployment_token = TOKEN
    with TestClient(app) as client:
        user = loop.run_until_complete(
            auth_store.create_user(username="viewer", password="pw", role="user")
        )
        session = loop.run_until_complete(auth_store.create_session(user.id, ttl_seconds=60))
        client.cookies.set(settings.session_cookie_name, session)
        yield client
    settings.deployment_token = original_token
    loop.run_until_complete(recorder.stop())
    loop.close()


def event_payload(**overrides):
    payload = {
        "event_id": "evt-1",
        "hostname": "Node-01.Lab",
        "status": "installer_started",
        "reported_at": "2026-10-07T12:00:00Z",
        "ip_addresses": ["192.0.2.10"],
        "mac_addresses": ["AA:BB:CC:DD:EE:FF"],
        "message": "installer started",
    }
    payload.update(overrides)
    return payload


def test_main_app_exposes_deployment_routes():
    from app.main import app

    paths = app.openapi()["paths"]
    assert paths["/api/deployments/events"].keys() == {"post"}
    assert paths["/api/deployments"].keys() == {"get"}
    assert paths["/api/deployments/{hostname}"].keys() == {"get"}
    assert paths["/api/deployments/{hostname}/history"].keys() == {"get"}


def test_installer_auth_rejects_missing_wrong_and_unconfigured_token(deployment_client):
    assert (
        deployment_client.post("/api/deployments/events", json=event_payload()).status_code == 401
    )
    response = deployment_client.post(
        "/api/deployments/events",
        headers={"Authorization": "Bearer wrong"},
        json=event_payload(),
    )
    assert response.status_code == 401
    assert TOKEN not in response.text

    response = deployment_client.post(
        "/api/deployments/events",
        headers={b"authorization": b"Bearer t\xf6ken"},
        json=event_payload(),
    )
    assert response.status_code == 401

    settings.deployment_token = None
    response = deployment_client.post("/api/deployments/events", headers=AUTH, json=event_payload())
    assert response.status_code == 503
    assert TOKEN not in response.text
    settings.deployment_token = TOKEN


def test_upsert_is_idempotent_and_reinstall_increments_attempt(deployment_client):
    first = deployment_client.post("/api/deployments/events", headers=AUTH, json=event_payload())
    assert first.status_code == 201
    assert first.json()["hostname"] == "node-01.lab"
    assert first.json()["attempt"] == 1
    assert first.json()["status"] == "installer_started"

    duplicate = deployment_client.post(
        "/api/deployments/events",
        headers=AUTH,
        json=event_payload(hostname="node-01.lab"),
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == first.json()["id"]

    complete = deployment_client.post(
        "/api/deployments/events",
        headers=AUTH,
        json=event_payload(
            event_id="evt-2",
            hostname="NODE-01.LAB",
            status="install_complete",
            reported_at="2026-10-07T12:10:00Z",
        ),
    )
    assert complete.json()["attempt"] == 1

    reinstall = deployment_client.post(
        "/api/deployments/events",
        headers=AUTH,
        json=event_payload(
            event_id="evt-3",
            hostname="node-01.lab",
            reported_at="2026-10-08T12:00:00Z",
        ),
    )
    assert reinstall.json()["attempt"] == 2

    nodes = deployment_client.get("/api/deployments").json()
    assert len(nodes) == 1
    assert nodes[0]["attempt"] == 2
    assert nodes[0]["stage"] == "installer_started"

    history = deployment_client.get("/api/deployments/node-01.lab/history").json()
    assert [item["stage"] for item in history] == [
        "installer_started",
        "install_complete",
        "installer_started",
    ]


def test_history_orders_by_event_time_and_old_event_does_not_regress_status(deployment_client):
    later = event_payload(
        event_id="late",
        status="packages_installed",
        reported_at="2026-10-07T12:30:00Z",
    )
    earlier = event_payload(
        event_id="early",
        status="storage_configured",
        reported_at="2026-10-07T12:20:00Z",
    )
    assert (
        deployment_client.post("/api/deployments/events", headers=AUTH, json=later).status_code
        == 201
    )
    assert (
        deployment_client.post("/api/deployments/events", headers=AUTH, json=earlier).status_code
        == 201
    )

    detail = deployment_client.get("/api/deployments/node-01.lab")
    assert detail.status_code == 200
    assert detail.json()["stage"] == "packages_installed"
    history = deployment_client.get("/api/deployments/node-01.lab/history").json()
    assert [event["stage"] for event in history] == ["storage_configured", "packages_installed"]


def test_status_reads_require_existing_user_session(deployment_client):
    deployment_client.cookies.clear()
    assert deployment_client.get("/api/deployments").status_code == 401
    assert deployment_client.get("/api/deployments/node-01.lab").status_code == 401
    assert deployment_client.get("/api/deployments/node-01.lab/history").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"hostname": "bad_host"},
        {"status": "unknown"},
        {"reported_at": "2026-10-07T12:00:00"},
        {"mac_addresses": ["not-a-mac"]},
        {"message": "x" * 1025},
        {"unexpected": "field"},
    ],
)
def test_invalid_or_unbounded_payload_is_rejected(deployment_client, changes):
    response = deployment_client.post(
        "/api/deployments/events", headers=AUTH, json=event_payload(**changes)
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_initialize_migrates_existing_database_without_data_loss(tmp_path: Path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE legacy_data (value TEXT NOT NULL)")
        conn.execute("INSERT INTO legacy_data VALUES ('preserved')")

    store = DeploymentStore(str(db))
    await store.initialize()
    await store.initialize()

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT value FROM legacy_data").fetchone() == ("preserved",)
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert {"deployment_nodes", "deployment_events", "deployment_schema_migrations"} <= tables
        assert conn.execute("SELECT version FROM deployment_schema_migrations").fetchall() == [(1,)]
