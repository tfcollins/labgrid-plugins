import asyncio
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.auth.store import AuthStore
from app.recorder import Recorder


@pytest.fixture
def app_with_users(tmp_path):
    from app.main import app

    db = str(tmp_path / "h.db")
    loop = asyncio.new_event_loop()
    r = Recorder(db)
    loop.run_until_complete(r.start())
    store = AuthStore(db)

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.auth_store = store
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:
        yield c, store, loop
    app.router.lifespan_context = original
    loop.run_until_complete(r.stop())
    loop.close()


def _login_as(c, store, loop, role="admin"):
    u = loop.run_until_complete(
        store.create_user(username=f"caller-{role}", password="pw", role=role)
    )
    c.post("/api/auth/login", json={"username": u.username, "password": "pw"})
    return u


def test_list_users_admin_only(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="user")
    assert c.get("/api/users").status_code == 403


def test_list_users_returns_all(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    loop.run_until_complete(store.create_user(username="bob", password="pw", role="user"))
    r = c.get("/api/users")
    assert r.status_code == 200
    names = [u["username"] for u in r.json()]
    assert "bob" in names


def test_create_user(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    r = c.post(
        "/api/users",
        json={"username": "new", "password": "pw", "role": "user"},
    )
    assert r.status_code == 201
    assert r.json()["username"] == "new"


def test_create_user_duplicate_returns_409(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    c.post("/api/users", json={"username": "dup", "password": "pw", "role": "user"})
    r = c.post("/api/users", json={"username": "dup", "password": "pw", "role": "user"})
    assert r.status_code == 409


def test_delete_user(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    u = loop.run_until_complete(store.create_user(username="kill", password="p", role="user"))
    r = c.delete(f"/api/users/{u.id}")
    assert r.status_code == 204
    assert loop.run_until_complete(store.get_user_by_id(u.id)) is None


def test_set_password(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    u = loop.run_until_complete(store.create_user(username="pw", password="old", role="user"))
    r = c.put(f"/api/users/{u.id}/password", json={"password": "new"})
    assert r.status_code == 204


def test_set_role(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    u = loop.run_until_complete(store.create_user(username="r", password="p", role="user"))
    r = c.put(f"/api/users/{u.id}/role", json={"role": "admin"})
    assert r.status_code == 204
    fresh = loop.run_until_complete(store.get_user_by_id(u.id))
    assert fresh.role == "admin"


def test_set_disabled(app_with_users):
    c, store, loop = app_with_users
    _login_as(c, store, loop, role="admin")
    u = loop.run_until_complete(store.create_user(username="d", password="p", role="user"))
    r = c.put(f"/api/users/{u.id}/disabled", json={"disabled": True})
    assert r.status_code == 204
    fresh = loop.run_until_complete(store.get_user_by_id(u.id))
    assert fresh.disabled_at is not None
