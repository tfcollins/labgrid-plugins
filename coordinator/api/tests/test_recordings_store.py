import pytest
import pytest_asyncio

from app.auth.store import AuthStore
from app.recorder import Recorder
from app.recordings.store import Recording, RecordingStore


@pytest_asyncio.fixture
async def stores(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    yield AuthStore(db), RecordingStore(db)
    await r.stop()


@pytest.mark.asyncio
async def test_create_recording(stores):
    auth, recs = stores
    u = await auth.create_user(username="alice", password="pw", role="user")
    rec = await recs.create(
        place_name="vcu118",
        resource_name="serial",
        user_id=u.id,
        file_path="/tmp/x.cast",
    )
    assert isinstance(rec, Recording)
    assert rec.id
    assert rec.byte_count == 0
    assert rec.ended_at is None


@pytest.mark.asyncio
async def test_finish_recording(stores):
    auth, recs = stores
    u = await auth.create_user(username="a", password="p", role="user")
    r = await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/tmp/x.cast")
    await recs.finish(r.id, byte_count=42, terminated_reason="normal")
    fresh = await recs.get(r.id)
    assert fresh.byte_count == 42
    assert fresh.terminated_reason == "normal"
    assert fresh.ended_at is not None


@pytest.mark.asyncio
async def test_list_recordings_filters(stores):
    auth, recs = stores
    u1 = await auth.create_user(username="a", password="p", role="user")
    u2 = await auth.create_user(username="b", password="p", role="user")
    await recs.create(place_name="p1", resource_name="r", user_id=u1.id, file_path="/x")
    await recs.create(place_name="p2", resource_name="r", user_id=u2.id, file_path="/y")
    all_recs = await recs.list()
    assert len(all_recs) == 2
    only_a = await recs.list(user_id=u1.id)
    assert len(only_a) == 1 and only_a[0].user_id == u1.id
    only_p2 = await recs.list(place_name="p2")
    assert len(only_p2) == 1 and only_p2[0].place_name == "p2"


@pytest.mark.asyncio
async def test_delete_recording(stores):
    auth, recs = stores
    u = await auth.create_user(username="a", password="p", role="user")
    r = await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/x")
    await recs.delete(r.id)
    assert await recs.get(r.id) is None


@pytest.mark.asyncio
async def test_total_bytes_per_place(stores):
    auth, recs = stores
    u = await auth.create_user(username="a", password="p", role="user")
    r1 = await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/a")
    r2 = await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/b")
    await recs.finish(r1.id, byte_count=100)
    await recs.finish(r2.id, byte_count=200)
    assert await recs.total_bytes_for_place("p") == 300


@pytest.mark.asyncio
async def test_list_older_than(stores):
    auth, recs = stores
    u = await auth.create_user(username="a", password="p", role="user")
    r1 = await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/a")
    await recs.create(place_name="p", resource_name="r", user_id=u.id, file_path="/b")
    import time

    import aiosqlite

    async with aiosqlite.connect(recs.db_path) as conn:
        await conn.execute("UPDATE recordings SET started_at = ? WHERE id = ?", (1.0, r1.id))
        await conn.commit()
    old = await recs.list_older_than(threshold=time.time() - 1)
    assert {r.id for r in old} == {r1.id}
