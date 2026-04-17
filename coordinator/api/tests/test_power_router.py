"""Tests for /api/places/{name}/power/{action}.

Replaces labgrid-client on PATH with a small shell stub so tests don't
need a real coordinator or power device. The stub echoes its arguments
and prints a deterministic status for `power get`.
"""

import os
import stat

import pytest


@pytest.fixture
def fake_labgrid_client(tmp_path, monkeypatch):
    """Install a fake `labgrid-client` on PATH that prints args + fake state."""
    script = tmp_path / "labgrid-client"
    script.write_text(
        "#!/bin/sh\n"
        'echo "ARGS: $@"\n'
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    get) echo "main: on"; exit 0;;\n'
        '    on|off|cycle) echo "done"; exit 0;;\n'
        "  esac\n"
        "done\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    return script


def test_unauth_blocked(authed_lifespan_client, fake_labgrid_client):
    r = authed_lifespan_client.post("/api/places/vcu118-lab1/power/on")
    assert r.status_code == 401


def test_non_owner_blocked(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    c.login("alice")
    # alice did NOT acquire
    r = c.post("/api/places/vcu118-lab1/power/on")
    assert r.status_code == 409


def test_invalid_action_400(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    alice = None
    # login() creates the user; look it up
    import asyncio

    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire("vcu118-lab1", alice.id))
    loop.close()
    r = c.post("/api/places/vcu118-lab1/power/boom")
    assert r.status_code == 400


def test_owner_can_power_on(authed_lifespan_client, fake_labgrid_client):
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
    r = c.post("/api/places/vcu118-lab1/power/on")
    assert r.status_code == 200
    assert r.json()["action"] == "on"


def test_get_parses_state(authed_lifespan_client, fake_labgrid_client):
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
    r = c.post("/api/places/vcu118-lab1/power/get")
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "get"
    assert body["state"] == "on"


def test_resource_name_passed_to_cli(authed_lifespan_client, fake_labgrid_client):
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
    r = c.post("/api/places/vcu118-lab1/power/on?resource=pdu1")
    assert r.status_code == 200
    assert "--name pdu1" in r.json()["stdout"]


def test_admin_can_power_on_anothers_place(authed_lifespan_client, fake_labgrid_client):
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
    r = c.post("/api/places/vcu118-lab1/power/off")
    assert r.status_code == 200
