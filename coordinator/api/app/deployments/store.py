"""SQLite-backed node deployment status store."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite

SCHEMA_VERSION = 1
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS deployment_schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS deployment_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hostname TEXT NOT NULL UNIQUE COLLATE NOCASE,
    attempt INTEGER NOT NULL DEFAULT 1,
    current_stage TEXT NOT NULL,
    current_event_at REAL NOT NULL,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    ip_addresses TEXT NOT NULL DEFAULT '[]',
    mac_addresses TEXT NOT NULL DEFAULT '[]',
    message TEXT,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_deployment_nodes_updated
    ON deployment_nodes(last_seen_at DESC);
CREATE TABLE IF NOT EXISTS deployment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id INTEGER NOT NULL REFERENCES deployment_nodes(id) ON DELETE CASCADE,
    event_id TEXT,
    attempt INTEGER NOT NULL,
    stage TEXT NOT NULL,
    event_at REAL NOT NULL,
    received_at REAL NOT NULL,
    ip_addresses TEXT NOT NULL DEFAULT '[]',
    mac_addresses TEXT NOT NULL DEFAULT '[]',
    message TEXT,
    details TEXT,
    UNIQUE(node_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_deployment_events_node_time
    ON deployment_events(node_id, event_at, id);
"""


@dataclass(frozen=True)
class DeploymentNode:
    hostname: str
    attempt: int
    current_stage: str
    current_event_at: float
    first_seen_at: float
    last_seen_at: float
    ip_addresses: list[str]
    mac_addresses: list[str]
    message: str | None
    details: dict[str, Any] | None


@dataclass(frozen=True)
class DeploymentEvent:
    id: int
    event_id: str | None
    hostname: str
    attempt: int
    stage: str
    event_at: float
    received_at: float
    ip_addresses: list[str]
    mac_addresses: list[str]
    message: str | None
    details: dict[str, Any] | None


def _json_load(value: str | None, fallback):
    if value is None:
        return fallback
    return json.loads(value)


def _node(row) -> DeploymentNode:
    return DeploymentNode(
        hostname=row[0],
        attempt=row[1],
        current_stage=row[2],
        current_event_at=row[3],
        first_seen_at=row[4],
        last_seen_at=row[5],
        ip_addresses=_json_load(row[6], []),
        mac_addresses=_json_load(row[7], []),
        message=row[8],
        details=_json_load(row[9], None),
    )


def _event(row) -> DeploymentEvent:
    return DeploymentEvent(
        id=row[0],
        event_id=row[1],
        hostname=row[2],
        attempt=row[3],
        stage=row[4],
        event_at=row[5],
        received_at=row[6],
        ip_addresses=_json_load(row[7], []),
        mac_addresses=_json_load(row[8], []),
        message=row[9],
        details=_json_load(row[10], None),
    )


_NODE_COLUMNS = (
    "hostname, attempt, current_stage, current_event_at, first_seen_at, last_seen_at, "
    "ip_addresses, mac_addresses, message, details"
)
_EVENT_COLUMNS = (
    "e.id, e.event_id, n.hostname, e.attempt, e.stage, e.event_at, e.received_at, "
    "e.ip_addresses, e.mac_addresses, e.message, e.details"
)


class DeploymentStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        """Apply additive deployment schema migrations."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.executescript(SCHEMA_SQL)
            await conn.execute(
                "INSERT OR IGNORE INTO deployment_schema_migrations (version, applied_at) "
                "VALUES (?, ?)",
                (SCHEMA_VERSION, time.time()),
            )
            await conn.commit()

    async def record_event(
        self,
        *,
        hostname: str,
        event_id: str | None,
        stage: str,
        event_at: float,
        ip_addresses: list[str],
        mac_addresses: list[str],
        message: str | None,
        details: dict[str, Any] | None,
    ) -> DeploymentEvent:
        """Atomically upsert a node and append an installer event.

        A repeated event_id for a node returns the original event. A new
        install_started event begins another attempt unless the node is already
        at install_started, making transport retries safe even without an ID.
        """
        received_at = time.time()
        ip_json = json.dumps(ip_addresses, separators=(",", ":"), sort_keys=True)
        mac_json = json.dumps(mac_addresses, separators=(",", ":"), sort_keys=True)
        details_json = (
            json.dumps(details, separators=(",", ":"), sort_keys=True, allow_nan=False)
            if details is not None
            else None
        )
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA foreign_keys = ON")
            await conn.execute("BEGIN IMMEDIATE")
            cur = await conn.execute(
                "SELECT id, attempt, current_stage, current_event_at "
                "FROM deployment_nodes WHERE hostname = ? COLLATE NOCASE",
                (hostname,),
            )
            existing = await cur.fetchone()

            if existing is not None and event_id is not None:
                cur = await conn.execute(
                    f"SELECT {_EVENT_COLUMNS} FROM deployment_events e "
                    "JOIN deployment_nodes n ON n.id = e.node_id "
                    "WHERE e.node_id = ? AND e.event_id = ?",
                    (existing[0], event_id),
                )
                duplicate = await cur.fetchone()
                if duplicate is not None:
                    await conn.commit()
                    return _event(duplicate)

            if existing is None:
                attempt = 1
                cur = await conn.execute(
                    "INSERT INTO deployment_nodes "
                    "(hostname, attempt, current_stage, current_event_at, first_seen_at, "
                    "last_seen_at, ip_addresses, mac_addresses, message, details) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        hostname,
                        attempt,
                        stage,
                        event_at,
                        received_at,
                        received_at,
                        ip_json,
                        mac_json,
                        message,
                        details_json,
                    ),
                )
                node_id = cur.lastrowid
            else:
                node_id, attempt, current_stage, current_event_at = existing
                if stage == "installer_started" and current_stage != "installer_started":
                    attempt += 1
                    update_current = True
                else:
                    update_current = event_at >= current_event_at
                if update_current:
                    await conn.execute(
                        "UPDATE deployment_nodes SET attempt = ?, current_stage = ?, "
                        "current_event_at = ?, last_seen_at = ?, ip_addresses = ?, "
                        "mac_addresses = ?, message = ?, details = ? WHERE id = ?",
                        (
                            attempt,
                            stage,
                            event_at,
                            received_at,
                            ip_json,
                            mac_json,
                            message,
                            details_json,
                            node_id,
                        ),
                    )
                else:
                    await conn.execute(
                        "UPDATE deployment_nodes SET last_seen_at = ? WHERE id = ?",
                        (received_at, node_id),
                    )

            cur = await conn.execute(
                "INSERT INTO deployment_events "
                "(node_id, event_id, attempt, stage, event_at, received_at, ip_addresses, "
                "mac_addresses, message, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    node_id,
                    event_id,
                    attempt,
                    stage,
                    event_at,
                    received_at,
                    ip_json,
                    mac_json,
                    message,
                    details_json,
                ),
            )
            inserted_id = cur.lastrowid
            await conn.commit()
            cur = await conn.execute(
                f"SELECT {_EVENT_COLUMNS} FROM deployment_events e "
                "JOIN deployment_nodes n ON n.id = e.node_id WHERE e.id = ?",
                (inserted_id,),
            )
            return _event(await cur.fetchone())

    async def list_nodes(self) -> list[DeploymentNode]:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM deployment_nodes ORDER BY last_seen_at DESC, hostname"
            )
            return [_node(row) for row in await cur.fetchall()]

    async def get_node(self, hostname: str) -> DeploymentNode | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                f"SELECT {_NODE_COLUMNS} FROM deployment_nodes WHERE hostname = ? COLLATE NOCASE",
                (hostname,),
            )
            row = await cur.fetchone()
            return _node(row) if row else None

    async def history(self, hostname: str) -> list[DeploymentEvent] | None:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT id FROM deployment_nodes WHERE hostname = ? COLLATE NOCASE",
                (hostname,),
            )
            node = await cur.fetchone()
            if node is None:
                return None
            cur = await conn.execute(
                f"SELECT {_EVENT_COLUMNS} FROM deployment_events e "
                "JOIN deployment_nodes n ON n.id = e.node_id WHERE e.node_id = ? "
                "ORDER BY e.event_at, e.id",
                (node[0],),
            )
            return [_event(row) for row in await cur.fetchall()]
