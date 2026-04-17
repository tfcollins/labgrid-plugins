"""SQLite-backed recordings DAL."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import aiosqlite


@dataclass
class Recording:
    id: str
    place_name: str
    resource_name: str
    user_id: int
    started_at: float
    ended_at: float | None
    byte_count: int
    file_path: str
    terminated_reason: str | None


_COLS = (
    "id, place_name, resource_name, user_id, started_at, ended_at, "
    "byte_count, file_path, terminated_reason"
)


def _row(r) -> Recording:
    return Recording(
        id=r[0],
        place_name=r[1],
        resource_name=r[2],
        user_id=r[3],
        started_at=r[4],
        ended_at=r[5],
        byte_count=r[6],
        file_path=r[7],
        terminated_reason=r[8],
    )


class RecordingStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def create(
        self,
        *,
        place_name: str,
        resource_name: str,
        user_id: int,
        file_path: str,
    ) -> Recording:
        rid = str(uuid.uuid4())
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                f"INSERT INTO recordings ({_COLS}) VALUES (?, ?, ?, ?, ?, NULL, 0, ?, NULL)",
                (rid, place_name, resource_name, user_id, now, file_path),
            )
            await conn.commit()
            cur = await conn.execute(f"SELECT {_COLS} FROM recordings WHERE id = ?", (rid,))
            return _row(await cur.fetchone())

    async def finish(
        self,
        recording_id: str,
        *,
        byte_count: int,
        terminated_reason: str | None = "normal",
    ) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE recordings SET ended_at = ?, byte_count = ?, "
                "terminated_reason = ? WHERE id = ?",
                (time.time(), byte_count, terminated_reason, recording_id),
            )
            await conn.commit()

    async def get(self, recording_id: str) -> Recording | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_COLS} FROM recordings WHERE id = ?", (recording_id,)
            )
            row = await cur.fetchone()
        return _row(row) if row else None

    async def list(
        self,
        *,
        user_id: int | None = None,
        place_name: str | None = None,
        resource_name: str | None = None,
        limit: int = 200,
    ) -> list[Recording]:
        clauses = []
        params: list = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if place_name is not None:
            clauses.append("place_name = ?")
            params.append(place_name)
        if resource_name is not None:
            clauses.append("resource_name = ?")
            params.append(resource_name)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT {_COLS} FROM recordings{where} ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def delete(self, recording_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
            await conn.commit()

    async def total_bytes_for_place(self, place_name: str) -> int:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT COALESCE(SUM(byte_count), 0) FROM recordings WHERE place_name = ?",
                (place_name,),
            )
            (n,) = await cur.fetchone()
        return int(n)

    async def list_older_than(self, *, threshold: float) -> list[Recording]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_COLS} FROM recordings WHERE started_at < ? ORDER BY started_at",
                (threshold,),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]
