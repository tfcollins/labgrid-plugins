import pytest
import pytest_asyncio

from app.auth.store import AuthStore
from app.recorder import Recorder
from app.recordings.retention import sweep_retention
from app.recordings.store import RecordingStore


@pytest_asyncio.fixture
async def setup(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    auth = AuthStore(db)
    rs = RecordingStore(db)
    u = await auth.create_user(username="u", password="p", role="user")
    yield tmp_path, rs, u.id
    await r.stop()


@pytest.mark.asyncio
async def test_sweeps_old_recordings(setup):
    tmp_path, rs, uid = setup
    f = tmp_path / "old.cast"
    f.write_text("x")
    rec = await rs.create(place_name="p", resource_name="r", user_id=uid, file_path=str(f))
    await rs.finish(rec.id, byte_count=1)
    import aiosqlite

    async with aiosqlite.connect(rs.db_path) as conn:
        await conn.execute("UPDATE recordings SET started_at = ? WHERE id = ?", (1.0, rec.id))
        await conn.commit()
    deleted = await sweep_retention(
        rs,
        retention_days=1,
        max_bytes_per_place=10**12,
    )
    assert deleted >= 1
    assert not f.exists()
    assert await rs.get(rec.id) is None


@pytest.mark.asyncio
async def test_sweeps_excess_bytes_per_place(setup):
    tmp_path, rs, uid = setup
    files = []
    for i in range(3):
        f = tmp_path / f"r{i}.cast"
        f.write_text("x" * 100)
        rec = await rs.create(place_name="p", resource_name="r", user_id=uid, file_path=str(f))
        await rs.finish(rec.id, byte_count=100)
        files.append((rec.id, f))
        import aiosqlite

        async with aiosqlite.connect(rs.db_path) as conn:
            await conn.execute(
                "UPDATE recordings SET started_at = ? WHERE id = ?", (1000 + i, rec.id)
            )
            await conn.commit()
    deleted = await sweep_retention(rs, retention_days=99999, max_bytes_per_place=150)
    assert deleted >= 1
    assert not files[0][1].exists()
