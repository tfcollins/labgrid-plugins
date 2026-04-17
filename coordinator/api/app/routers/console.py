from __future__ import annotations

import logging
import os

import aiosqlite
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import settings
from ..console.manager import ConsoleManager
from ..places.store import PlaceAcquisitionStore
from ..recordings.writer import CastWriter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["console"])


def _store(app) -> PlaceAcquisitionStore:
    return app.state.place_acq_store


def _manager(app) -> ConsoleManager:
    return app.state.console_manager


@router.websocket("/places/{place_name}/resources/{resource_name}/console")
async def console_ws(websocket: WebSocket, place_name: str, resource_name: str):
    sid = websocket.cookies.get(settings.session_cookie_name)
    auth_store = websocket.app.state.auth_store
    user = await auth_store.resolve_session(sid) if sid else None
    if user is None:
        await websocket.close(code=1008)
        return

    acq_store = _store(websocket.app)
    acq = await acq_store.get(place_name)
    if acq is None or acq.user_id != user.id:
        await websocket.close(code=4403)
        return

    coord = websocket.app.state.coordinator
    resource = None
    if hasattr(coord, "get_resource"):
        resource = coord.get_resource(place_name, resource_name)
    if resource is None:
        for r in coord.get_resources():
            if r.name == resource_name:
                resource = r
                break
    if resource is None or resource.cls != "NetworkSerialPort":
        await websocket.close(code=1011)
        return

    host = resource.params.get("host")
    port = resource.params.get("port")
    if host is None or port is None:
        await websocket.close(code=1011)
        return

    mgr = _manager(websocket.app)
    mgr.cancel_grace(place_name, resource_name)

    rec_store = getattr(websocket.app.state, "recording_store", None)
    existing = mgr.get(place_name, resource_name)
    writer = None
    rec_id = None
    if rec_store is not None and (existing is None or existing.is_closed):
        os.makedirs(settings.recordings_dir, exist_ok=True)
        rec = await rec_store.create(
            place_name=place_name,
            resource_name=resource_name,
            user_id=user.id,
            file_path="",
        )
        rec_id = rec.id
        path = os.path.join(settings.recordings_dir, f"{rec.id}.cast")
        writer = CastWriter(path, title=f"{place_name}/{resource_name}")
        await writer.start()
        async with aiosqlite.connect(rec_store.db_path) as conn:
            await conn.execute("UPDATE recordings SET file_path = ? WHERE id = ?", (path, rec.id))
            await conn.commit()

    try:
        session = await mgr.get_or_create(
            place_name,
            resource_name,
            host=host,
            port=int(port),
            recorder=writer if writer is not None else (existing.recorder if existing else None),
        )
    except OSError as e:
        if writer is not None:
            await writer.close()
            if rec_id is not None:
                await rec_store.finish(
                    rec_id, byte_count=writer.byte_count, terminated_reason="error"
                )
        logger.warning("exporter unreachable: %s", e)
        await websocket.close(code=1011)
        return

    if writer is not None and rec_id is not None:
        session.recording_id = rec_id  # type: ignore[attr-defined]

    await websocket.accept()
    try:
        await session.run(websocket)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("console run error: %s", e)
    finally:
        mgr.arm_grace(place_name, resource_name)
