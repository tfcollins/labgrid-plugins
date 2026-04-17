import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import current_user, optional_user, require_admin
from app.auth.store import AuthStore
from app.config import settings
from app.recorder import Recorder


@pytest.fixture
def app_with_auth(tmp_path):
    db = str(tmp_path / "h.db")
    import asyncio

    loop = asyncio.new_event_loop()
    r = Recorder(db)
    loop.run_until_complete(r.start())
    store = AuthStore(db)

    app = FastAPI()
    app.state.auth_store = store

    @app.get("/me")
    async def me(user=Depends(current_user)):
        return {"username": user.username, "role": user.role}

    @app.get("/admin")
    async def admin_only(user=Depends(require_admin)):
        return {"username": user.username}

    @app.get("/maybe")
    async def maybe(user=Depends(optional_user)):
        return {"username": user.username if user else None}

    yield app, store, loop
    loop.run_until_complete(r.stop())
    loop.close()


def test_current_user_no_cookie_returns_401(app_with_auth):
    app, _store, _loop = app_with_auth
    c = TestClient(app)
    r = c.get("/me")
    assert r.status_code == 401


def test_current_user_invalid_cookie_returns_401(app_with_auth):
    app, _store, _loop = app_with_auth
    c = TestClient(app)
    c.cookies.set(settings.session_cookie_name, "bogus")
    r = c.get("/me")
    assert r.status_code == 401


def test_current_user_valid_cookie_returns_user(app_with_auth):
    app, store, loop = app_with_auth
    u = loop.run_until_complete(store.create_user(username="alice", password="pw", role="user"))
    sid = loop.run_until_complete(store.create_session(u.id, ttl_seconds=60))
    c = TestClient(app)
    c.cookies.set(settings.session_cookie_name, sid)
    r = c.get("/me")
    assert r.status_code == 200
    assert r.json() == {"username": "alice", "role": "user"}


def test_require_admin_rejects_non_admin(app_with_auth):
    app, store, loop = app_with_auth
    u = loop.run_until_complete(store.create_user(username="bob", password="pw", role="user"))
    sid = loop.run_until_complete(store.create_session(u.id, ttl_seconds=60))
    c = TestClient(app)
    c.cookies.set(settings.session_cookie_name, sid)
    r = c.get("/admin")
    assert r.status_code == 403


def test_require_admin_allows_admin(app_with_auth):
    app, store, loop = app_with_auth
    u = loop.run_until_complete(store.create_user(username="carol", password="pw", role="admin"))
    sid = loop.run_until_complete(store.create_session(u.id, ttl_seconds=60))
    c = TestClient(app)
    c.cookies.set(settings.session_cookie_name, sid)
    r = c.get("/admin")
    assert r.status_code == 200


def test_optional_user_no_cookie_returns_none(app_with_auth):
    app, _store, _loop = app_with_auth
    c = TestClient(app)
    r = c.get("/maybe")
    assert r.status_code == 200
    assert r.json() == {"username": None}
