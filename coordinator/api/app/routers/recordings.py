import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..auth.dependencies import current_user, require_admin
from ..auth.store import User
from ..recordings.store import RecordingStore

router = APIRouter(tags=["recordings"], prefix="/recordings")


def _store(request: Request) -> RecordingStore:
    return request.app.state.recording_store


class RecordingOut(BaseModel):
    id: str
    place_name: str
    resource_name: str
    user_id: int
    started_at: float
    ended_at: float | None
    byte_count: int
    terminated_reason: str | None


def _to_out(r) -> RecordingOut:
    return RecordingOut(
        id=r.id,
        place_name=r.place_name,
        resource_name=r.resource_name,
        user_id=r.user_id,
        started_at=r.started_at,
        ended_at=r.ended_at,
        byte_count=r.byte_count,
        terminated_reason=r.terminated_reason,
    )


@router.get("", response_model=list[RecordingOut])
async def list_recordings(
    request: Request,
    place_name: str | None = None,
    resource_name: str | None = None,
    user: User = Depends(current_user),
):
    user_filter = None if user.role == "admin" else user.id
    rows = await _store(request).list(
        user_id=user_filter,
        place_name=place_name,
        resource_name=resource_name,
    )
    return [_to_out(r) for r in rows]


@router.get("/{rid}", response_model=RecordingOut)
async def get_recording(rid: str, request: Request, user: User = Depends(current_user)):
    rec = await _store(request).get(rid)
    if rec is None:
        raise HTTPException(status_code=404)
    if user.role != "admin" and rec.user_id != user.id:
        raise HTTPException(status_code=403)
    return _to_out(rec)


@router.get("/{rid}/cast")
async def download_cast(rid: str, request: Request, user: User = Depends(current_user)):
    rec = await _store(request).get(rid)
    if rec is None:
        raise HTTPException(status_code=404)
    if user.role != "admin" and rec.user_id != user.id:
        raise HTTPException(status_code=403)
    if not os.path.exists(rec.file_path):
        raise HTTPException(status_code=404, detail="cast file missing")
    return FileResponse(rec.file_path, media_type="application/json", filename=f"{rid}.cast")


@router.delete("/{rid}", status_code=204)
async def delete_recording(
    rid: str,
    request: Request,
    _admin: User = Depends(require_admin),
):
    rec = await _store(request).get(rid)
    if rec is None:
        return
    try:
        if rec.file_path and os.path.exists(rec.file_path):
            os.remove(rec.file_path)
    except OSError:
        pass
    await _store(request).delete(rid)
