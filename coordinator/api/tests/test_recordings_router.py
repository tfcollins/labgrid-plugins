import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.auth.store import AuthStore
from app.recorder import Recorder
from app.recordings.store import RecordingStore


@pytest.fixture
def rec_app(tmp_path):
    from app.main import app

    db = str(tmp_path / "h.db")
    loop = asyncio.new_event_loop()
    rec = Recorder(db)
    loop.run_until_complete(rec.start())
    auth = AuthStore(db)
    rstore = RecordingStore(db)

    @asynccontextmanager
    async def _ls(_app):
        _app.state.auth_store = auth
        _app.state.recording_store = rstore
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _ls
    with TestClient(app) as c:

        def login(name, role="user"):
            loop.run_until_complete(auth.create_user(username=name, password="pw", role=role))
            c.post("/api/auth/login", json={"username": name, "password": "pw"})

        c.login = login
        c.loop = loop
        c.store = rstore
        yield c
    app.router.lifespan_context = original
    loop.run_until_complete(rec.stop())
    loop.close()


def test_unauth_blocked(rec_app):
    assert rec_app.get("/api/recordings").status_code == 401


def test_user_sees_own_recordings(rec_app):
    c = rec_app
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    alice = c.loop.run_until_complete(_AS(c.store.db_path).get_user_by_username("alice"))
    bob = c.loop.run_until_complete(
        _AS(c.store.db_path).create_user(username="bob", password="p", role="user")
    )
    c.loop.run_until_complete(
        c.store.create(place_name="p", resource_name="r", user_id=alice.id, file_path="/a")
    )
    c.loop.run_until_complete(
        c.store.create(place_name="p", resource_name="r", user_id=bob.id, file_path="/b")
    )
    r = c.get("/api/recordings")
    data = r.json()
    assert all(item["user_id"] == alice.id for item in data)


def test_admin_sees_all(rec_app):
    c = rec_app
    c.login("rooty", role="admin")
    from app.auth.store import AuthStore as _AS

    a = c.loop.run_until_complete(
        _AS(c.store.db_path).create_user(username="a", password="p", role="user")
    )
    b = c.loop.run_until_complete(
        _AS(c.store.db_path).create_user(username="b", password="p", role="user")
    )
    c.loop.run_until_complete(
        c.store.create(place_name="p", resource_name="r", user_id=a.id, file_path="/a")
    )
    c.loop.run_until_complete(
        c.store.create(place_name="p", resource_name="r", user_id=b.id, file_path="/b")
    )
    r = c.get("/api/recordings")
    assert len(r.json()) == 2


def test_download_streams_file(rec_app, tmp_path):
    c = rec_app
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    alice = c.loop.run_until_complete(_AS(c.store.db_path).get_user_by_username("alice"))
    cast_path = tmp_path / "x.cast"
    cast_path.write_text('{"version":2}\n[0,"o","hi"]\n')
    rec = c.loop.run_until_complete(
        c.store.create(
            place_name="p", resource_name="r", user_id=alice.id, file_path=str(cast_path)
        )
    )
    r = c.get(f"/api/recordings/{rec.id}/cast")
    assert r.status_code == 200
    assert b"hi" in r.content


def test_delete_admin_only(rec_app, tmp_path):
    c = rec_app
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    alice = c.loop.run_until_complete(_AS(c.store.db_path).get_user_by_username("alice"))
    cast_path = tmp_path / "x.cast"
    cast_path.write_text("x")
    rec = c.loop.run_until_complete(
        c.store.create(
            place_name="p", resource_name="r", user_id=alice.id, file_path=str(cast_path)
        )
    )
    r = c.delete(f"/api/recordings/{rec.id}")
    assert r.status_code == 403
    c.post("/api/auth/logout")
    c.login("rooty", role="admin")
    r = c.delete(f"/api/recordings/{rec.id}")
    assert r.status_code == 204
    assert not cast_path.exists()
