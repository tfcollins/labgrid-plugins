"""FastAPI dependencies for authn/authz."""

from __future__ import annotations

from fastapi import HTTPException, Request

from ..config import settings
from .store import AuthStore, User


def _store(request: Request) -> AuthStore:
    return request.app.state.auth_store


async def optional_user(request: Request) -> User | None:
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        return None
    return await _store(request).resolve_session(cookie)


async def current_user(request: Request) -> User:
    user = await optional_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


async def require_admin(request: Request) -> User:
    user = await current_user(request)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin role required")
    return user
