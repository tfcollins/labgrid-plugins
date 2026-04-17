"""Tests for /api/places/{name}/sdmux/{action}.

Replaces labgrid-client on PATH with a shell stub that prints args and a
deterministic mode for `sd-mux get`.
"""

import asyncio
import os
import stat

import pytest


@pytest.fixture
def fake_labgrid_client(tmp_path, monkeypatch):
    script = tmp_path / "labgrid-client"
    script.write_text(
        "#!/bin/sh\n"
        'echo "ARGS: $@"\n'
        'for a in "$@"; do\n'
        '  case "$a" in\n'
        '    get) echo "host"; exit 0;;\n'
        "    dut|host|off|client) exit 0;;\n"
        "  esac\n"
        "done\n"
        "exit 0\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    return script


def _login_and_acquire(c, place="vcu118-lab1"):
    from app.auth.store import AuthStore as _AS

    c.login("alice")
    loop = asyncio.new_event_loop()
    alice = loop.run_until_complete(
        _AS(c.app.state.place_acq_store.db_path).get_user_by_username("alice")
    )
    loop.run_until_complete(c.app.state.place_acq_store.acquire(place, alice.id))
    loop.close()


def test_unauth_blocked(authed_lifespan_client, fake_labgrid_client):
    r = authed_lifespan_client.post("/api/places/vcu118-lab1/sdmux/host")
    assert r.status_code == 401


def test_non_owner_blocked(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    c.login("alice")
    r = c.post("/api/places/vcu118-lab1/sdmux/host")
    assert r.status_code == 409


def test_invalid_action_400(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    _login_and_acquire(c)
    r = c.post("/api/places/vcu118-lab1/sdmux/boom")
    assert r.status_code == 400


def test_owner_can_switch_modes(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    _login_and_acquire(c)
    for action in ("dut", "host", "off", "client"):
        r = c.post(f"/api/places/vcu118-lab1/sdmux/{action}")
        assert r.status_code == 200, (action, r.text)
        assert r.json()["action"] == action


def test_get_parses_mode(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    _login_and_acquire(c)
    r = c.post("/api/places/vcu118-lab1/sdmux/get")
    assert r.status_code == 200
    assert r.json()["action"] == "get"
    assert r.json()["mode"] == "host"


def test_resource_name_passed_to_cli(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    _login_and_acquire(c)
    r = c.post("/api/places/vcu118-lab1/sdmux/host?resource=mux1")
    assert r.status_code == 200
    assert "--name mux1" in r.json()["stdout"]


def test_admin_can_switch_anothers_place(authed_lifespan_client, fake_labgrid_client):
    c = authed_lifespan_client
    _login_and_acquire(c)
    c.post("/api/auth/logout")
    c.login("root", role="admin")
    r = c.post("/api/places/vcu118-lab1/sdmux/dut")
    assert r.status_code == 200
