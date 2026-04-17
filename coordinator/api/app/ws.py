"""WebSocket endpoint for real-time coordinator updates."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts updates."""

    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, message: dict):
        text = json.dumps(message)
        stale = []
        for ws in self._connections:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)


manager = ConnectionManager()


def _broadcast_callback(message: dict):
    """Called from the gRPC message pump (sync context) to schedule a broadcast."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(manager.broadcast(message))
    except RuntimeError:
        pass


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    coordinator = ws.app.state.coordinator

    # Wire up the broadcast callback if not already set
    if coordinator.on_update is None:
        coordinator.on_update = _broadcast_callback

    await manager.connect(ws)
    try:
        # Send initial state snapshot
        places = [p.model_dump() for p in coordinator.get_places()]
        resources = [r.model_dump() for r in coordinator.get_resources()]
        await ws.send_text(
            json.dumps(
                {
                    "type": "initial_state",
                    "data": {"places": places, "resources": resources},
                }
            )
        )

        # Keep connection alive until client disconnects
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
