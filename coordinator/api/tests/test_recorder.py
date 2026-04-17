import asyncio

import pytest
import pytest_asyncio

from app.recorder import Recorder


@pytest_asyncio.fixture
async def recorder(tmp_path):
    db_path = str(tmp_path / "test.db")
    rec = Recorder(db_path)
    await rec.start()
    yield rec
    await rec.stop()


@pytest.mark.asyncio
async def test_schema_created(recorder):
    """Tables exist after start."""
    async with recorder._get_db() as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in await cursor.fetchall()]
    assert "events" in tables
    assert "place_sessions" in tables
    assert "resource_availability" in tables


@pytest.mark.asyncio
async def test_recordings_table_created(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    try:
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='recordings'"
            )
            assert (await cur.fetchone()) is not None
    finally:
        await r.stop()


@pytest.mark.asyncio
async def test_record_place_created(recorder):
    await recorder.record_event("place_created", place_name="vcu118-lab1")
    await asyncio.sleep(0.1)  # let queue drain

    async with recorder._get_db() as db:
        cursor = await db.execute("SELECT event_type, place_name FROM events")
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "place_created"
    assert rows[0][1] == "vcu118-lab1"


@pytest.mark.asyncio
async def test_record_place_acquired_creates_session(recorder):
    await recorder.record_event("place_acquired", place_name="vcu118-lab1", user="travis")
    await asyncio.sleep(0.1)

    async with recorder._get_db() as db:
        cursor = await db.execute("SELECT place_name, user, released_at FROM place_sessions")
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "vcu118-lab1"
    assert rows[0][1] == "travis"
    assert rows[0][2] is None  # not released yet


@pytest.mark.asyncio
async def test_record_place_released_closes_session(recorder):
    await recorder.record_event("place_acquired", place_name="vcu118-lab1", user="travis")
    await asyncio.sleep(0.1)
    await recorder.record_event("place_released", place_name="vcu118-lab1", user="travis")
    await asyncio.sleep(0.1)

    async with recorder._get_db() as db:
        cursor = await db.execute(
            "SELECT released_at FROM place_sessions WHERE place_name='vcu118-lab1'"
        )
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] is not None


@pytest.mark.asyncio
async def test_record_resource_online(recorder):
    await recorder.record_event("resource_online", resource_key="exp1/GRP/NetworkService/net")
    await asyncio.sleep(0.1)

    async with recorder._get_db() as db:
        cursor = await db.execute("SELECT resource_key, available FROM resource_availability")
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "exp1/GRP/NetworkService/net"
    assert rows[0][1] == 1


@pytest.mark.asyncio
async def test_record_resource_offline(recorder):
    await recorder.record_event("resource_offline", resource_key="exp1/GRP/NetworkService/net")
    await asyncio.sleep(0.1)

    async with recorder._get_db() as db:
        cursor = await db.execute("SELECT available FROM resource_availability")
        rows = await cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 0


@pytest.mark.asyncio
async def test_get_events_paginated(recorder):
    for i in range(10):
        await recorder.record_event("place_created", place_name=f"place-{i}")
    # Allow queue to drain fully - 10 sequential writes need time
    await asyncio.sleep(1.0)

    events, total = await recorder.get_events(limit=3, offset=0)
    assert total == 10
    assert len(events) == 3
    # Most recent first
    assert events[0]["place_name"] == "place-9"


@pytest.mark.asyncio
async def test_get_events_filtered_by_type(recorder):
    await recorder.record_event("place_created", place_name="p1")
    await recorder.record_event("place_acquired", place_name="p1", user="alice")
    await asyncio.sleep(0.1)

    events, total = await recorder.get_events(event_type="place_acquired")
    assert total == 1
    assert events[0]["event_type"] == "place_acquired"


@pytest.mark.asyncio
async def test_users_and_sessions_tables_created(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    try:
        async with r._lock:  # noqa: SLF001
            import aiosqlite

            async with aiosqlite.connect(db) as conn:
                cur = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('users','sessions') ORDER BY name"
                )
                rows = [r[0] for r in await cur.fetchall()]
        assert rows == ["sessions", "users"]
    finally:
        await r.stop()


@pytest.mark.asyncio
async def test_place_acquisitions_table_created(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    try:
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            cur = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='place_acquisitions'"
            )
            assert (await cur.fetchone()) is not None
    finally:
        await r.stop()
