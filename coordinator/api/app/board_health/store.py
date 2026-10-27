"""SQLite-backed board health check store."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite
from croniter import croniter

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS board_health_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    cron_expression TEXT NOT NULL,
    places TEXT NOT NULL,          -- JSON list of place names, or '["*"]'
    image TEXT,                    -- Golden boot image override (nullable)
    power_down INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_run_at REAL,
    next_run_at REAL
);

CREATE TABLE IF NOT EXISTS board_health_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_name TEXT NOT NULL,
    status TEXT NOT NULL,          -- 'pending', 'running', 'passed', 'failed', 'busy', 'cancelled'
    started_at REAL NOT NULL,
    finished_at REAL,
    duration REAL,
    boot_strategy TEXT,
    image TEXT,
    ip_address TEXT,
    iiod_reachable INTEGER DEFAULT 0,
    error_message TEXT,
    log_output TEXT,
    trigger TEXT NOT NULL,         -- 'manual', 'scheduled'
    triggered_by TEXT,             -- username or schedule name
    schedule_id INTEGER REFERENCES board_health_schedules(id) ON DELETE SET NULL,
    drivers TEXT
);

CREATE INDEX IF NOT EXISTS idx_board_health_runs_place ON board_health_runs(place_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_board_health_runs_status ON board_health_runs(status);
"""


@dataclass(frozen=True)
class HealthCheckSchedule:
    id: int
    name: str
    description: str | None
    cron_expression: str
    places: list[str]
    image: str | None
    power_down: bool
    enabled: bool
    created_at: float
    updated_at: float
    last_run_at: float | None
    next_run_at: float | None


@dataclass(frozen=True)
class HealthCheckRun:
    id: int
    place_name: str
    status: str
    started_at: float
    finished_at: float | None
    duration: float | None
    boot_strategy: str | None
    image: str | None
    ip_address: str | None
    iiod_reachable: bool
    error_message: str | None
    log_output: str | None
    trigger: str
    triggered_by: str | None
    schedule_id: int | None
    drivers: list[str] | None = None


def _calc_next_run(cron_expr: str, base_time: float) -> float | None:
    try:
        iter = croniter(cron_expr, base_time)
        return float(iter.get_next())
    except Exception as e:
        logger.warning("Invalid cron expression %r: %s", cron_expr, e)
        return None


def _row_to_schedule(row: tuple) -> HealthCheckSchedule:
    places_raw = row[4]
    try:
        places = json.loads(places_raw) if places_raw else ["*"]
    except Exception:
        places = ["*"]

    return HealthCheckSchedule(
        id=row[0],
        name=row[1],
        description=row[2],
        cron_expression=row[3],
        places=places,
        image=row[5],
        power_down=bool(row[6]),
        enabled=bool(row[7]),
        created_at=row[8],
        updated_at=row[9],
        last_run_at=row[10],
        next_run_at=row[11],
    )


def _row_to_run(row: tuple) -> HealthCheckRun:
    drivers: list[str] | None = None
    if len(row) > 15 and row[15]:
        try:
            drivers = json.loads(row[15])
        except Exception:
            drivers = None

    return HealthCheckRun(
        id=row[0],
        place_name=row[1],
        status=row[2],
        started_at=row[3],
        finished_at=row[4],
        duration=row[5],
        boot_strategy=row[6],
        image=row[7],
        ip_address=row[8],
        iiod_reachable=bool(row[9]),
        error_message=row[10],
        log_output=row[11],
        trigger=row[12],
        triggered_by=row[13],
        schedule_id=row[14],
        drivers=drivers,
    )


class BoardHealthStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.executescript(SCHEMA_SQL)
            try:
                await conn.execute("ALTER TABLE board_health_runs ADD COLUMN drivers TEXT")
            except Exception:
                pass
            await conn.commit()

    # --- Schedule operations ---

    async def create_schedule(
        self,
        *,
        name: str,
        description: str | None = None,
        cron_expression: str,
        places: list[str],
        image: str | None = None,
        power_down: bool = True,
        enabled: bool = True,
    ) -> HealthCheckSchedule:
        now = time.time()
        next_run = _calc_next_run(cron_expression, now) if enabled else None
        places_json = json.dumps(places)

        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                INSERT INTO board_health_schedules
                (name, description, cron_expression, places, image, power_down, enabled, created_at, updated_at, last_run_at, next_run_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    name,
                    description,
                    cron_expression,
                    places_json,
                    image,
                    1 if power_down else 0,
                    1 if enabled else 0,
                    now,
                    now,
                    next_run,
                ),
            )
            schedule_id = cur.lastrowid
            await conn.commit()
            return await self.get_schedule(schedule_id)  # type: ignore[return-value]

    async def update_schedule(
        self,
        schedule_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        cron_expression: str | None = None,
        places: list[str] | None = None,
        image: str | None = None,
        power_down: bool | None = None,
        enabled: bool | None = None,
    ) -> HealthCheckSchedule | None:
        existing = await self.get_schedule(schedule_id)
        if not existing:
            return None

        now = time.time()
        new_name = name if name is not None else existing.name
        new_desc = description if description is not None else existing.description
        new_cron = cron_expression if cron_expression is not None else existing.cron_expression
        new_places = json.dumps(places) if places is not None else json.dumps(existing.places)
        new_image = image if image is not None else existing.image
        new_power_down = 1 if (power_down if power_down is not None else existing.power_down) else 0
        new_enabled = 1 if (enabled if enabled is not None else existing.enabled) else 0

        new_next_run = _calc_next_run(new_cron, now) if new_enabled else None

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE board_health_schedules
                SET name = ?, description = ?, cron_expression = ?, places = ?, image = ?,
                    power_down = ?, enabled = ?, updated_at = ?, next_run_at = ?
                WHERE id = ?
                """,
                (
                    new_name,
                    new_desc,
                    new_cron,
                    new_places,
                    new_image,
                    new_power_down,
                    new_enabled,
                    now,
                    new_next_run,
                    schedule_id,
                ),
            )
            await conn.commit()

        return await self.get_schedule(schedule_id)

    async def delete_schedule(self, schedule_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "DELETE FROM board_health_schedules WHERE id = ?", (schedule_id,)
            )
            await conn.commit()
            return cur.rowcount > 0

    async def get_schedule(self, schedule_id: int) -> HealthCheckSchedule | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                SELECT id, name, description, cron_expression, places, image, power_down, enabled,
                       created_at, updated_at, last_run_at, next_run_at
                FROM board_health_schedules
                WHERE id = ?
                """,
                (schedule_id,),
            )
            row = await cur.fetchone()
            return _row_to_schedule(row) if row else None

    async def list_schedules(self) -> list[HealthCheckSchedule]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                SELECT id, name, description, cron_expression, places, image, power_down, enabled,
                       created_at, updated_at, last_run_at, next_run_at
                FROM board_health_schedules
                ORDER BY created_at DESC
                """
            )
            rows = await cur.fetchall()
            return [_row_to_schedule(row) for row in rows]

    async def get_due_schedules(self, now: float) -> list[HealthCheckSchedule]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                SELECT id, name, description, cron_expression, places, image, power_down, enabled,
                       created_at, updated_at, last_run_at, next_run_at
                FROM board_health_schedules
                WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
                """,
                (now,),
            )
            rows = await cur.fetchall()
            return [_row_to_schedule(row) for row in rows]

    async def advance_schedule_time(self, schedule_id: int, last_run_at: float) -> None:
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            return
        next_run = (
            _calc_next_run(schedule.cron_expression, last_run_at) if schedule.enabled else None
        )
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE board_health_schedules
                SET last_run_at = ?, next_run_at = ?
                WHERE id = ?
                """,
                (last_run_at, next_run, schedule_id),
            )
            await conn.commit()

    # --- Run operations ---

    async def create_run(
        self,
        *,
        place_name: str,
        trigger: str,
        triggered_by: str | None = None,
        schedule_id: int | None = None,
        image: str | None = None,
        boot_strategy: str | None = None,
    ) -> HealthCheckRun:
        now = time.time()
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                INSERT INTO board_health_runs
                (place_name, status, started_at, finished_at, duration, boot_strategy, image,
                 ip_address, iiod_reachable, error_message, log_output, trigger, triggered_by, schedule_id)
                VALUES (?, 'pending', ?, NULL, NULL, ?, ?, NULL, 0, NULL, '', ?, ?, ?)
                """,
                (place_name, now, boot_strategy, image, trigger, triggered_by, schedule_id),
            )
            run_id = cur.lastrowid
            await conn.commit()
            return await self.get_run(run_id)  # type: ignore[return-value]

    async def start_run(
        self, run_id: int, *, boot_strategy: str | None = None, image: str | None = None
    ) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE board_health_runs
                SET status = 'running',
                    boot_strategy = COALESCE(?, boot_strategy),
                    image = COALESCE(?, image)
                WHERE id = ?
                """,
                (boot_strategy, image, run_id),
            )
            await conn.commit()

    async def append_run_log(self, run_id: int, text: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE board_health_runs
                SET log_output = COALESCE(log_output, '') || ?
                WHERE id = ?
                """,
                (text, run_id),
            )
            await conn.commit()

    async def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        duration: float,
        ip_address: str | None = None,
        iiod_reachable: bool = False,
        error_message: str | None = None,
        log_output: str | None = None,
        boot_strategy: str | None = None,
        image: str | None = None,
        drivers: list[str] | None = None,
    ) -> HealthCheckRun | None:
        now = time.time()
        drivers_json = json.dumps(drivers) if drivers is not None else None
        async with aiosqlite.connect(self.db_path) as conn:
            if log_output is not None:
                await conn.execute(
                    """
                    UPDATE board_health_runs
                    SET status = ?, finished_at = ?, duration = ?, ip_address = ?,
                        iiod_reachable = ?, error_message = ?, log_output = ?,
                        boot_strategy = COALESCE(?, boot_strategy),
                        image = COALESCE(?, image),
                        drivers = COALESCE(?, drivers)
                    WHERE id = ?
                    """,
                    (
                        status,
                        now,
                        duration,
                        ip_address,
                        1 if iiod_reachable else 0,
                        error_message,
                        log_output,
                        boot_strategy,
                        image,
                        drivers_json,
                        run_id,
                    ),
                )
            else:
                await conn.execute(
                    """
                    UPDATE board_health_runs
                    SET status = ?, finished_at = ?, duration = ?, ip_address = ?,
                        iiod_reachable = ?, error_message = ?,
                        boot_strategy = COALESCE(?, boot_strategy),
                        image = COALESCE(?, image),
                        drivers = COALESCE(?, drivers)
                    WHERE id = ?
                    """,
                    (
                        status,
                        now,
                        duration,
                        ip_address,
                        1 if iiod_reachable else 0,
                        error_message,
                        boot_strategy,
                        image,
                        drivers_json,
                        run_id,
                    ),
                )
            await conn.commit()
        return await self.get_run(run_id)

    async def get_run(self, run_id: int) -> HealthCheckRun | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                SELECT id, place_name, status, started_at, finished_at, duration, boot_strategy,
                       image, ip_address, iiod_reachable, error_message, log_output, trigger,
                       triggered_by, schedule_id, drivers
                FROM board_health_runs
                WHERE id = ?
                """,
                (run_id,),
            )
            row = await cur.fetchone()
            return _row_to_run(row) if row else None

    async def list_runs(
        self,
        *,
        place_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[HealthCheckRun]:
        clauses = []
        params: list[Any] = []
        if place_name:
            clauses.append("place_name = ?")
            params.append(place_name)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, place_name, status, started_at, finished_at, duration, boot_strategy,
                   image, ip_address, iiod_reachable, error_message, log_output, trigger,
                   triggered_by, schedule_id, drivers
            FROM board_health_runs
            {where}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
            return [_row_to_run(row) for row in rows]

    async def get_latest_run_per_place(self) -> dict[str, HealthCheckRun]:
        """Return a mapping of place_name -> latest HealthCheckRun."""
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                """
                SELECT r.id, r.place_name, r.status, r.started_at, r.finished_at, r.duration,
                       r.boot_strategy, r.image, r.ip_address, r.iiod_reachable, r.error_message,
                       r.log_output, r.trigger, r.triggered_by, r.schedule_id, r.drivers
                FROM board_health_runs r
                INNER JOIN (
                    SELECT place_name, MAX(started_at) as max_started
                    FROM board_health_runs
                    GROUP BY place_name
                ) latest ON r.place_name = latest.place_name AND r.started_at = latest.max_started
                """
            )
            rows = await cur.fetchall()
            return {row[1]: _row_to_run(row) for row in rows}
