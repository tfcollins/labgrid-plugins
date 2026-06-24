"""Tests for POST /api/places/{name}/recover.

Stubs out resolve_strategy + generate_env_yaml on the recovery module and
puts a fake `adi-lg` on PATH so no real coordinator or hardware is needed.
"""

import asyncio
import os
import stat

import pytest

import app.routers.recovery as recovery


@pytest.fixture(autouse=True)
def _stub_strategy_and_env(monkeypatch, tmp_path):
    monkeypatch.setattr(
        recovery, "resolve_strategy", lambda tags, classes: recovery.RECOVERY_STRATEGY
    )
    monkeypatch.setattr(
        recovery, "generate_env_yaml", lambda place, resources, tier: "targets: {}\n"
    )
    fake = tmp_path / "adi-lg"
    fake.write_text('#!/bin/sh\necho recovered "$@"\n')
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")


def test_recover_requires_auth(authed_lifespan_client):
    r = authed_lifespan_client.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 401


def test_recover_not_acquired(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    # alice did NOT acquire the place
    r = c.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 409


def test_recover_non_owner_forbidden(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    # bob (non-admin) tries to recover alice's place
    c.post("/api/auth/logout")
    c.login("bob")
    r = c.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 403


def test_recover_owner_ok(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    import asyncio

    from app.auth.store import AuthStore as _AS

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    r = c.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["state"] == "sd_flash_done"


def test_recover_admin_ok(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    import asyncio

    from app.auth.store import AuthStore as _AS

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    c.post("/api/auth/logout")
    c.login("root", role="admin")
    r = c.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 200


def test_recover_invalid_state(authed_lifespan_client):
    c = authed_lifespan_client
    c.login("alice")
    import asyncio

    from app.auth.store import AuthStore as _AS

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    r = c.post("/api/places/vcu118-lab1/recover?state=shell")
    assert r.status_code == 400


def test_recover_wrong_strategy_422(authed_lifespan_client, monkeypatch):
    c = authed_lifespan_client
    c.login("alice")
    import asyncio

    from app.auth.store import AuthStore as _AS

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    # Override resolve_strategy to return None (wrong strategy)
    monkeypatch.setattr(recovery, "resolve_strategy", lambda tags, classes: None)
    r = c.post("/api/places/vcu118-lab1/recover")
    assert r.status_code == 422
