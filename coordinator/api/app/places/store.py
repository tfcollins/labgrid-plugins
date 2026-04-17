"""SQLite-backed per-user place acquisition tracking."""

from __future__ import annotations

import time
from dataclasses import dataclass

import aiosqlite


@dataclass
class Acquisition:
    place_name: str
    user_id: int
    acquired_at: float
    last_seen_at: float
    grace_until: float | None


def _row(r) -> Acquisition:
    return Acquisition(
        place_name=r[0],
        user_id=r[1],
        acquired_at=r[2],
        last_seen_at=r[3],
        grace_until=r[4],
    )


class PlaceAcquisitionStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def acquire(self, place_name: str, user_id: int) -> Acquisition:
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT user_id FROM place_acquisitions WHERE place_name = ?",
                (place_name,),
            )
            row = await cur.fetchone()
            if row is not None and row[0] != user_id:
                raise ValueError(f"place '{place_name}' already acquired by another user")
            if row is not None:
                await conn.execute(
                    "UPDATE place_acquisitions SET grace_until = NULL, last_seen_at = ? "
                    "WHERE place_name = ?",
                    (now, place_name),
                )
            else:
                await conn.execute(
                    "INSERT INTO place_acquisitions "
                    "(place_name, user_id, acquired_at, last_seen_at, grace_until) "
                    "VALUES (?, ?, ?, ?, NULL)",
                    (place_name, user_id, now, now),
                )
            await conn.commit()
            cur = await conn.execute(
                "SELECT place_name, user_id, acquired_at, last_seen_at, grace_until "
                "FROM place_acquisitions WHERE place_name = ?",
                (place_name,),
            )
            return _row(await cur.fetchone())

    async def release(self, place_name: str, *, user_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT user_id FROM place_acquisitions WHERE place_name = ?", (place_name,)
            )
            row = await cur.fetchone()
            if row is None:
                return
            if row[0] != user_id:
                raise PermissionError(f"place '{place_name}' not owned by user {user_id}")
            await conn.execute("DELETE FROM place_acquisitions WHERE place_name = ?", (place_name,))
            await conn.commit()

    async def force_release(self, place_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("DELETE FROM place_acquisitions WHERE place_name = ?", (place_name,))
            await conn.commit()

    async def get(self, place_name: str) -> Acquisition | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT place_name, user_id, acquired_at, last_seen_at, grace_until "
                "FROM place_acquisitions WHERE place_name = ?",
                (place_name,),
            )
            row = await cur.fetchone()
        return _row(row) if row else None

    async def list_all(self) -> list[Acquisition]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT place_name, user_id, acquired_at, last_seen_at, grace_until "
                "FROM place_acquisitions ORDER BY place_name"
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]

    async def set_grace(self, place_name: str, *, grace_until: float) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE place_acquisitions SET grace_until = ? WHERE place_name = ?",
                (grace_until, place_name),
            )
            await conn.commit()

    async def clear_grace(self, place_name: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "UPDATE place_acquisitions SET grace_until = NULL, last_seen_at = ? "
                "WHERE place_name = ?",
                (time.time(), place_name),
            )
            await conn.commit()

    async def list_expired_grace(self, *, now: float) -> list[Acquisition]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT place_name, user_id, acquired_at, last_seen_at, grace_until "
                "FROM place_acquisitions "
                "WHERE grace_until IS NOT NULL AND grace_until <= ? "
                "ORDER BY grace_until",
                (now,),
            )
            rows = await cur.fetchall()
        return [_row(r) for r in rows]
