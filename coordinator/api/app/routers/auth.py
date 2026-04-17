import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..auth.dependencies import current_user
from ..auth.oidc import OIDCClient, OIDCDisabled
from ..auth.passwords import verify_password
from ..auth.store import AuthStore, User
from ..config import settings

router = APIRouter(tags=["auth"], prefix="/auth")


def _store(request: Request) -> AuthStore:
    return request.app.state.auth_store


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    username: str
    role: str


def _to_public(u: User) -> UserPublic:
    return UserPublic(username=u.username, role=u.role)


def _set_cookie(response: Response, sid: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=UserPublic)
async def login(body: LoginRequest, request: Request, response: Response):
    store = _store(request)
    user = await store.get_user_by_username(body.username)
    if user is None or user.disabled_at is not None or user.password_hash is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    sid = await store.create_session(user.id, ttl_seconds=settings.session_ttl_hours * 3600)
    _set_cookie(response, sid)
    return _to_public(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response):
    sid = request.cookies.get(settings.session_cookie_name)
    if sid:
        await _store(request).delete_session(sid)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserPublic)
async def me(user: User = Depends(current_user)):
    return _to_public(user)


class BootstrapRequest(BaseModel):
    token: str
    username: str
    password: str


@router.post("/bootstrap", status_code=201, response_model=UserPublic)
async def bootstrap(body: BootstrapRequest, request: Request):
    store = _store(request)
    token = getattr(request.app.state, "bootstrap_token", None)
    if not token or await store.user_count() > 0:
        raise HTTPException(status_code=410, detail="bootstrap already complete")
    if not secrets.compare_digest(token, body.token):
        raise HTTPException(status_code=403, detail="invalid bootstrap token")
    user = await store.create_user(username=body.username, password=body.password, role="admin")
    request.app.state.bootstrap_token = None
    return _to_public(user)


def _oidc(request: Request) -> OIDCClient:
    c = getattr(request.app.state, "oidc", None)
    if c is None or not c.enabled:
        raise HTTPException(status_code=404, detail="OIDC not configured")
    return c


def _callback_uri(request: Request) -> str:
    return str(request.url_for("oidc_callback"))


@router.get("/oidc/login")
async def oidc_login(request: Request):
    c = _oidc(request)
    try:
        await c.discover()
        url, _state = c.authorization_url(_callback_uri(request))
    except OIDCDisabled:
        raise HTTPException(status_code=404, detail="OIDC not configured") from None
    return RedirectResponse(url, status_code=307)


@router.get("/oidc/callback", name="oidc_callback")
async def oidc_callback(code: str, state: str, request: Request):
    c = _oidc(request)
    info = await c.exchange_code(code=code, redirect_uri=_callback_uri(request))
    store = _store(request)
    user = await store.get_user_by_oidc_subject(info.subject)
    if user is None:
        if not settings.oidc_auto_provision:
            raise HTTPException(status_code=403, detail="ask an admin to create your account")
        user = await store.create_user(
            username=info.username,
            password=None,
            role="user",
            oidc_subject=info.subject,
        )
    sid = await store.create_session(user.id, ttl_seconds=settings.session_ttl_hours * 3600)
    response = RedirectResponse("/", status_code=307)
    _set_cookie(response, sid)
    return response
