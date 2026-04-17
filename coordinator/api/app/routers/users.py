from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth.dependencies import require_admin
from ..auth.store import AuthStore, User

router = APIRouter(tags=["users"], prefix="/users")


def _store(request: Request) -> AuthStore:
    return request.app.state.auth_store


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    disabled: bool
    has_password: bool
    has_oidc: bool


def _to_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        role=u.role,
        disabled=u.disabled_at is not None,
        has_password=u.password_hash is not None,
        has_oidc=u.oidc_subject is not None,
    )


class CreateUserRequest(BaseModel):
    username: str
    password: str | None = None
    role: str


class SetPasswordRequest(BaseModel):
    password: str


class SetRoleRequest(BaseModel):
    role: str


class SetDisabledRequest(BaseModel):
    disabled: bool


@router.get("", response_model=list[UserOut])
async def list_users(request: Request, _admin: User = Depends(require_admin)):
    return [_to_out(u) for u in await _store(request).list_users()]


@router.post("", status_code=201, response_model=UserOut)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    _admin: User = Depends(require_admin),
):
    try:
        u = await _store(request).create_user(
            username=body.username,
            password=body.password,
            role=body.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _to_out(u)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    request: Request,
    _admin: User = Depends(require_admin),
):
    await _store(request).delete_user(user_id)


@router.put("/{user_id}/password", status_code=204)
async def set_password(
    user_id: int,
    body: SetPasswordRequest,
    request: Request,
    _admin: User = Depends(require_admin),
):
    await _store(request).set_password(user_id, body.password)


@router.put("/{user_id}/role", status_code=204)
async def set_role(
    user_id: int,
    body: SetRoleRequest,
    request: Request,
    _admin: User = Depends(require_admin),
):
    try:
        await _store(request).set_role(user_id, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{user_id}/disabled", status_code=204)
async def set_disabled(
    user_id: int,
    body: SetDisabledRequest,
    request: Request,
    _admin: User = Depends(require_admin),
):
    await _store(request).set_disabled(user_id, body.disabled)
