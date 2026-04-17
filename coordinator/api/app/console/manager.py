"""Per-resource ConsoleSession registry with a 60s grace timer."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .session import ConsoleSession

logger = logging.getLogger(__name__)


class ConsoleManager:
    def __init__(self, *, grace_seconds: float = 60.0):
        self.grace_seconds = grace_seconds
        self._sessions: dict[tuple[str, str], ConsoleSession] = {}
        self._grace_tasks: dict[tuple[str, str], asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self.on_grace_expired: Callable[[str, str], Awaitable[None] | None] | None = None
        self.on_session_dropped: (
            Callable[[str, str, ConsoleSession], Awaitable[None] | None] | None
        ) = None

    async def get_or_create(
        self,
        place: str,
        resource: str,
        *,
        host: str,
        port: int,
        recorder=None,
    ) -> ConsoleSession:
        key = (place, resource)
        async with self._lock:
            existing = self._sessions.get(key)
            if existing is not None and not existing.is_closed:
                return existing
            s = ConsoleSession(host=host, port=port, recorder=recorder)
            await s.connect()
            self._sessions[key] = s
            return s

    def get(self, place: str, resource: str) -> ConsoleSession | None:
        return self._sessions.get((place, resource))

    async def drop(self, place: str, resource: str) -> None:
        key = (place, resource)
        async with self._lock:
            t = self._grace_tasks.pop(key, None)
            if t is not None and not t.done():
                t.cancel()
            s = self._sessions.pop(key, None)
        if s is not None:
            await s.close()
            cb = self.on_session_dropped
            if cb is not None:
                try:
                    r = cb(place, resource, s)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception as e:
                    logger.warning("on_session_dropped failed: %s", e)

    def arm_grace(self, place: str, resource: str) -> None:
        key = (place, resource)
        existing = self._grace_tasks.pop(key, None)
        if existing is not None and not existing.done():
            existing.cancel()
        self._grace_tasks[key] = asyncio.create_task(self._grace_runner(place, resource))

    def cancel_grace(self, place: str, resource: str) -> None:
        key = (place, resource)
        t = self._grace_tasks.pop(key, None)
        if t is not None and not t.done():
            t.cancel()

    async def _grace_runner(self, place: str, resource: str) -> None:
        try:
            await asyncio.sleep(self.grace_seconds)
        except asyncio.CancelledError:
            return
        # Close the session directly without going through drop() to avoid
        # self-cancellation (drop() would call t.cancel() on this very task).
        key = (place, resource)
        async with self._lock:
            self._grace_tasks.pop(key, None)
            session = self._sessions.pop(key, None)
        if session is not None:
            await session.close()
            cb_drop = self.on_session_dropped
            if cb_drop is not None:
                try:
                    r = cb_drop(place, resource, session)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception as e:
                    logger.warning("on_session_dropped failed: %s", e)
        cb = self.on_grace_expired
        if cb is not None:
            try:
                r = cb(place, resource)
                if asyncio.iscoroutine(r):
                    await r
            except Exception as e:
                logger.warning("on_grace_expired callback failed: %s", e)

    async def shutdown(self) -> None:
        for t in list(self._grace_tasks.values()):
            t.cancel()
        items = list(self._sessions.items())
        self._sessions.clear()
        self._grace_tasks.clear()
        for (place, resource), s in items:
            await s.close()
            cb = self.on_session_dropped
            if cb is not None:
                try:
                    r = cb(place, resource, s)
                    if asyncio.iscoroutine(r):
                        await r
                except Exception:
                    pass
