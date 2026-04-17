"""SQLite-backed event recorder for coordinator history and statistics."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,
    place_name TEXT,
    resource_key TEXT,
    user TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_place ON events(place_name);

CREATE TABLE IF NOT EXISTS place_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_name TEXT NOT NULL,
    user TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    released_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sessions_place ON place_sessions(place_name);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON place_sessions(user);

CREATE TABLE IF NOT EXISTS resource_availability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_key TEXT NOT NULL,
    available INTEGER NOT NULL,
    changed_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_avail_resource ON resource_availability(resource_key);
CREATE INDEX IF NOT EXISTS idx_avail_changed ON resource_availability(changed_at);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin','user')),
    oidc_subject TEXT UNIQUE,
    created_at REAL NOT NULL,
    disabled_at REAL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    last_seen_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS place_acquisitions (
    place_name TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    acquired_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    grace_until REAL
);
CREATE INDEX IF NOT EXISTS idx_place_acq_user ON place_acquisitions(user_id);

CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    place_name TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at REAL NOT NULL,
    ended_at REAL,
    byte_count INTEGER NOT NULL DEFAULT 0,
    file_path TEXT NOT NULL,
    terminated_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_recordings_place ON recordings(place_name);
CREATE INDEX IF NOT EXISTS idx_recordings_user ON recordings(user_id);
CREATE INDEX IF NOT EXISTS idx_recordings_started ON recordings(started_at);
"""


class Recorder:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue()
        self._consumer_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def start(self):
        async with self._get_db() as db:
            await db.executescript(SCHEMA_SQL)
            await db.commit()
        self._consumer_task = asyncio.create_task(self._consume())
        logger.info("Recorder started with database at %s", self.db_path)

    async def stop(self):
        self._queue.put_nowait(None)
        if self._consumer_task:
            await self._consumer_task

    @asynccontextmanager
    async def _get_db(self):
        db = await aiosqlite.connect(self.db_path)
        db.row_factory = aiosqlite.Row
        try:
            yield db
        finally:
            await db.close()

    async def record_event(
        self,
        event_type: str,
        *,
        place_name: str | None = None,
        resource_key: str | None = None,
        user: str | None = None,
        details: str | None = None,
    ):
        self._queue.put_nowait(
            {
                "event_type": event_type,
                "place_name": place_name,
                "resource_key": resource_key,
                "user": user,
                "details": details,
                "timestamp": time.time(),
            }
        )

    async def _consume(self):
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                await self._write_event(item)
            except Exception:
                logger.exception("Failed to write event: %s", item)

    async def _write_event(self, event: dict):
        async with self._get_db() as db:
            await db.execute(
                "INSERT INTO events (timestamp, event_type, place_name, resource_key, user, details)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    event["timestamp"],
                    event["event_type"],
                    event["place_name"],
                    event["resource_key"],
                    event["user"],
                    event["details"],
                ),
            )

            et = event["event_type"]
            if et == "place_acquired" and event["place_name"] and event["user"]:
                await db.execute(
                    "INSERT INTO place_sessions (place_name, user, acquired_at) VALUES (?, ?, ?)",
                    (event["place_name"], event["user"], event["timestamp"]),
                )
            elif et == "place_released" and event["place_name"]:
                await db.execute(
                    "UPDATE place_sessions SET released_at = ?"
                    " WHERE place_name = ? AND released_at IS NULL",
                    (event["timestamp"], event["place_name"]),
                )
            elif et == "resource_online" and event["resource_key"]:
                await db.execute(
                    "INSERT INTO resource_availability (resource_key, available, changed_at)"
                    " VALUES (?, 1, ?)",
                    (event["resource_key"], event["timestamp"]),
                )
            elif et == "resource_offline" and event["resource_key"]:
                await db.execute(
                    "INSERT INTO resource_availability (resource_key, available, changed_at)"
                    " VALUES (?, 0, ?)",
                    (event["resource_key"], event["timestamp"]),
                )

            await db.commit()

    # --- Query methods ---

    async def get_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        event_type: str | None = None,
        place_name: str | None = None,
        since: float | None = None,
        until: float | None = None,
    ) -> tuple[list[dict], int]:
        conditions = []
        params: list = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if place_name:
            conditions.append("place_name = ?")
            params.append(place_name)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp <= ?")
            params.append(until)

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

        async with self._get_db() as db:
            cursor = await db.execute(f"SELECT COUNT(*) FROM events{where}", params)
            total = (await cursor.fetchone())[0]

            cursor = await db.execute(
                f"SELECT * FROM events{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
            rows = await cursor.fetchall()
            events = [dict(row) for row in rows]

        return events, total

    async def get_place_stats(self, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 86400
        async with self._get_db() as db:
            cursor = await db.execute(
                """
                SELECT
                    place_name,
                    COUNT(*) as total_sessions,
                    COALESCE(SUM(
                        CASE WHEN released_at IS NOT NULL
                            THEN released_at - acquired_at
                            ELSE ? - acquired_at
                        END
                    ), 0) as total_acquired_seconds,
                    (SELECT user FROM place_sessions ps2
                     WHERE ps2.place_name = place_sessions.place_name
                     ORDER BY acquired_at DESC LIMIT 1) as last_acquired_by
                FROM place_sessions
                WHERE acquired_at >= ?
                GROUP BY place_name
                ORDER BY total_acquired_seconds DESC
                """,
                (time.time(), cutoff),
            )
            rows = await cursor.fetchall()
            window = days * 86400
            return [
                {
                    "place_name": row["place_name"],
                    "total_sessions": row["total_sessions"],
                    "total_acquired_seconds": row["total_acquired_seconds"],
                    "utilization_percent": round(row["total_acquired_seconds"] / window * 100, 1),
                    "last_acquired_by": row["last_acquired_by"],
                }
                for row in rows
            ]

    async def get_place_sessions(self, place_name: str) -> list[dict]:
        async with self._get_db() as db:
            cursor = await db.execute(
                """
                SELECT user, acquired_at, released_at,
                    CASE WHEN released_at IS NOT NULL
                        THEN released_at - acquired_at
                        ELSE ? - acquired_at
                    END as duration_seconds
                FROM place_sessions
                WHERE place_name = ?
                ORDER BY acquired_at DESC
                """,
                (time.time(), place_name),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def get_resource_stats(self, days: int = 30) -> list[dict]:
        cutoff = time.time() - days * 86400
        window = days * 86400
        async with self._get_db() as db:
            cursor = await db.execute(
                "SELECT DISTINCT resource_key FROM resource_availability WHERE changed_at >= ?",
                (cutoff,),
            )
            keys = [row[0] for row in await cursor.fetchall()]

        results = []
        for key in keys:
            async with self._get_db() as db:
                cursor = await db.execute(
                    """
                    SELECT available, changed_at
                    FROM resource_availability
                    WHERE resource_key = ? AND changed_at >= ?
                    ORDER BY changed_at ASC
                    """,
                    (key, cutoff),
                )
                rows = await cursor.fetchall()

            online_seconds = 0.0
            now = time.time()
            for i, row in enumerate(rows):
                end = rows[i + 1]["changed_at"] if i + 1 < len(rows) else now
                if row["available"]:
                    online_seconds += end - row["changed_at"]

            offline_seconds = window - online_seconds
            results.append(
                {
                    "resource_key": key,
                    "uptime_percent": round(online_seconds / window * 100, 1),
                    "total_online_seconds": round(online_seconds, 1),
                    "total_offline_seconds": round(offline_seconds, 1),
                    "last_changed": rows[-1]["changed_at"] if rows else None,
                }
            )
        return results

    async def get_exporter_stats(self, days: int = 30) -> list[dict]:
        resource_stats = await self.get_resource_stats(days)
        by_exporter: dict[str, list[float]] = {}
        for rs in resource_stats:
            exporter = rs["resource_key"].split("/")[0]
            by_exporter.setdefault(exporter, []).append(rs["uptime_percent"])
        return [
            {
                "exporter": name,
                "resource_count": len(uptimes),
                "avg_uptime_percent": round(sum(uptimes) / len(uptimes), 1),
            }
            for name, uptimes in sorted(by_exporter.items())
        ]

    async def get_overview(self) -> dict:
        now = time.time()
        day_ago = now - 86400
        async with self._get_db() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp >= ?", (day_ago,)
            )
            total_events_24h = (await cursor.fetchone())[0]

            cursor = await db.execute(
                """
                SELECT AVG(
                    CASE WHEN released_at IS NOT NULL
                        THEN released_at - acquired_at
                        ELSE ? - acquired_at
                    END
                ) / 3600.0 as avg_hours
                FROM place_sessions
                WHERE acquired_at >= ?
                """,
                (now, day_ago),
            )
            row = await cursor.fetchone()
            avg_hours = round(row[0], 1) if row[0] else 0.0

            cursor = await db.execute(
                """
                SELECT CAST(strftime('%H', timestamp, 'unixepoch', 'localtime') AS INTEGER) as hour,
                       COUNT(*) as cnt
                FROM events
                WHERE timestamp >= ?
                GROUP BY hour
                ORDER BY cnt DESC
                LIMIT 1
                """,
                (day_ago,),
            )
            row = await cursor.fetchone()
            busiest_hour = row[0] if row else 0

            cursor = await db.execute(
                """
                SELECT place_name, COUNT(*) as cnt
                FROM events
                WHERE event_type = 'place_acquired' AND timestamp >= ?
                GROUP BY place_name
                ORDER BY cnt DESC
                LIMIT 1
                """,
                (day_ago,),
            )
            row = await cursor.fetchone()
            most_used = row[0] if row else None

        resource_stats = await self.get_resource_stats(1)
        avg_uptime = (
            round(sum(r["uptime_percent"] for r in resource_stats) / len(resource_stats), 1)
            if resource_stats
            else 100.0
        )

        return {
            "total_events_24h": total_events_24h,
            "avg_acquisition_duration_hours": avg_hours,
            "busiest_hour": busiest_hour,
            "most_used_place": most_used,
            "avg_uptime_percent": avg_uptime,
        }
