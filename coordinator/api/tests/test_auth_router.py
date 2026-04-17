import asyncio
from contextlib import asynccontextmanager

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.auth.store import AuthStore
from app.config import settings
from app.recorder import Recorder


@pytest.fixture
def authed_app(tmp_path):
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


def test_login_with_valid_credentials_sets_cookie(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(store.create_user(username="a", password="pw", role="user"))
    r = c.post("/api/auth/login", json={"username": "a", "password": "pw"})
    assert r.status_code == 200
    assert r.json() == {"username": "a", "role": "user"}
    assert settings.session_cookie_name in r.cookies


def test_login_with_bad_password_returns_401(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(store.create_user(username="a", password="pw", role="user"))
    r = c.post("/api/auth/login", json={"username": "a", "password": "wrong"})
    assert r.status_code == 401


def test_login_unknown_user_returns_401(authed_app):
    c, _store, _loop = authed_app
    r = c.post("/api/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_login_disabled_user_returns_401(authed_app):
    c, store, loop = authed_app
    u = loop.run_until_complete(store.create_user(username="d", password="pw", role="user"))
    loop.run_until_complete(store.set_disabled(u.id, True))
    r = c.post("/api/auth/login", json={"username": "d", "password": "pw"})
    assert r.status_code == 401


def test_me_returns_current_user(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(store.create_user(username="m", password="pw", role="admin"))
    c.post("/api/auth/login", json={"username": "m", "password": "pw"})
    r = c.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json() == {"username": "m", "role": "admin"}


def test_me_without_login_returns_401(authed_app):
    c, _, _ = authed_app
    r = c.get("/api/auth/me")
    assert r.status_code == 401


def test_logout_clears_session(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(store.create_user(username="x", password="pw", role="user"))
    c.post("/api/auth/login", json={"username": "x", "password": "pw"})
    r = c.post("/api/auth/logout")
    assert r.status_code == 204
    r = c.get("/api/auth/me")
    assert r.status_code == 401


def test_bootstrap_creates_first_admin(authed_app):
    c, store, loop = authed_app
    from app.auth.bootstrap import generate_bootstrap_token

    token = generate_bootstrap_token()
    c.app.state.bootstrap_token = token
    r = c.post(
        "/api/auth/bootstrap",
        json={"token": token, "username": "root", "password": "pw"},
    )
    assert r.status_code == 201
    assert r.json() == {"username": "root", "role": "admin"}
    users = loop.run_until_complete(store.list_users())
    assert len(users) == 1
    assert users[0].role == "admin"


def test_bootstrap_rejects_wrong_token(authed_app):
    c, _store, _loop = authed_app
    c.app.state.bootstrap_token = "secret"
    r = c.post(
        "/api/auth/bootstrap",
        json={"token": "wrong", "username": "root", "password": "pw"},
    )
    assert r.status_code == 403


def test_bootstrap_410_after_users_exist(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(store.create_user(username="x", password="p", role="admin"))
    c.app.state.bootstrap_token = "tok"
    r = c.post(
        "/api/auth/bootstrap",
        json={"token": "tok", "username": "y", "password": "p"},
    )
    assert r.status_code == 410


def test_bootstrap_410_when_no_token_configured(authed_app):
    c, _store, _loop = authed_app
    c.app.state.bootstrap_token = None
    r = c.post(
        "/api/auth/bootstrap",
        json={"token": "anything", "username": "y", "password": "p"},
    )
    assert r.status_code == 410


@respx.mock
def test_oidc_login_redirects_to_provider(authed_app, monkeypatch):
    c, _store, _loop = authed_app
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "userinfo_endpoint": "https://idp.example/userinfo",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    from app.auth.oidc import OIDCClient

    c.app.state.oidc = OIDCClient(
        issuer="https://idp.example/",
        client_id="abc",
        client_secret="xyz",
    )
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"].startswith("https://idp.example/authorize")


def test_oidc_login_404_when_disabled(authed_app):
    c, _, _ = authed_app
    from app.auth.oidc import OIDCClient

    c.app.state.oidc = OIDCClient(issuer=None, client_id=None, client_secret=None)
    r = c.get("/api/auth/oidc/login", follow_redirects=False)
    assert r.status_code == 404


@respx.mock
def test_oidc_callback_existing_user_logs_in(authed_app):
    c, store, loop = authed_app
    loop.run_until_complete(
        store.create_user(username="alice", password=None, role="user", oidc_subject="sub-1")
    )
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "userinfo_endpoint": "https://idp.example/userinfo",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    respx.post("https://idp.example/token").mock(
        return_value=Response(200, json={"access_token": "AT", "token_type": "Bearer"})
    )
    respx.get("https://idp.example/userinfo").mock(
        return_value=Response(200, json={"sub": "sub-1", "preferred_username": "alice"})
    )
    from app.auth.oidc import OIDCClient

    c.app.state.oidc = OIDCClient(
        issuer="https://idp.example/",
        client_id="abc",
        client_secret="xyz",
    )
    r = c.get("/api/auth/oidc/callback?code=CODE&state=ignored", follow_redirects=False)
    assert r.status_code == 307
    assert settings.session_cookie_name in r.cookies


@respx.mock
def test_oidc_callback_new_user_rejected_without_auto_provision(authed_app, monkeypatch):
    c, _store, _loop = authed_app
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "userinfo_endpoint": "https://idp.example/userinfo",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    respx.post("https://idp.example/token").mock(
        return_value=Response(200, json={"access_token": "AT"})
    )
    respx.get("https://idp.example/userinfo").mock(
        return_value=Response(200, json={"sub": "newsub", "preferred_username": "new"})
    )
    monkeypatch.setattr(settings, "oidc_auto_provision", False)
    from app.auth.oidc import OIDCClient

    c.app.state.oidc = OIDCClient(
        issuer="https://idp.example/",
        client_id="abc",
        client_secret="xyz",
    )
    r = c.get("/api/auth/oidc/callback?code=CODE&state=ignored", follow_redirects=False)
    assert r.status_code == 403


@respx.mock
def test_oidc_callback_auto_provisions_when_enabled(authed_app, monkeypatch):
    c, store, loop = authed_app
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "userinfo_endpoint": "https://idp.example/userinfo",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    respx.post("https://idp.example/token").mock(
        return_value=Response(200, json={"access_token": "AT"})
    )
    respx.get("https://idp.example/userinfo").mock(
        return_value=Response(200, json={"sub": "subA", "preferred_username": "newby"})
    )
    monkeypatch.setattr(settings, "oidc_auto_provision", True)
    from app.auth.oidc import OIDCClient

    c.app.state.oidc = OIDCClient(
        issuer="https://idp.example/",
        client_id="abc",
        client_secret="xyz",
    )
    r = c.get("/api/auth/oidc/callback?code=CODE&state=ignored", follow_redirects=False)
    assert r.status_code == 307
    assert settings.session_cookie_name in r.cookies
    user = loop.run_until_complete(store.get_user_by_oidc_subject("subA"))
    assert user is not None
    assert user.role == "user"
