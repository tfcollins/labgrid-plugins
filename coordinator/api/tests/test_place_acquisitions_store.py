import pytest
import pytest_asyncio

from app.auth.store import AuthStore
from app.places.store import Acquisition, PlaceAcquisitionStore
from app.recorder import Recorder


@pytest_asyncio.fixture
async def stores(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    yield AuthStore(db), PlaceAcquisitionStore(db)
    await r.stop()


@pytest.mark.asyncio
async def test_acquire_records_owner(stores):
    auth, places = stores
    u = await auth.create_user(username="alice", password="pw", role="user")
    a = await places.acquire("vcu118", u.id)
    assert isinstance(a, Acquisition)
    assert a.place_name == "vcu118"
    assert a.user_id == u.id
    assert a.grace_until is None


@pytest.mark.asyncio
async def test_acquire_when_owned_by_other_raises(stores):
    auth, places = stores
    u1 = await auth.create_user(username="a", password="p", role="user")
    u2 = await auth.create_user(username="b", password="p", role="user")
    await places.acquire("p", u1.id)
    with pytest.raises(ValueError, match="already acquired"):
        await places.acquire("p", u2.id)


@pytest.mark.asyncio
async def test_reacquire_by_same_owner_clears_grace(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p", u.id)
    await places.set_grace("p", grace_until=999.0)
    a = await places.acquire("p", u.id)
    assert a.grace_until is None


@pytest.mark.asyncio
async def test_release_by_owner(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p", u.id)
    await places.release("p", user_id=u.id)
    assert await places.get("p") is None


@pytest.mark.asyncio
async def test_release_by_non_owner_raises(stores):
    auth, places = stores
    u1 = await auth.create_user(username="a", password="p", role="user")
    u2 = await auth.create_user(username="b", password="p", role="user")
    await places.acquire("p", u1.id)
    with pytest.raises(PermissionError):
        await places.release("p", user_id=u2.id)


@pytest.mark.asyncio
async def test_force_release(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p", u.id)
    await places.force_release("p")
    assert await places.get("p") is None


@pytest.mark.asyncio
async def test_set_and_clear_grace(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p", u.id)
    await places.set_grace("p", grace_until=1234.0)
    a = await places.get("p")
    assert a.grace_until == 1234.0
    await places.clear_grace("p")
    a = await places.get("p")
    assert a.grace_until is None


@pytest.mark.asyncio
async def test_list_all(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p1", u.id)
    await places.acquire("p2", u.id)
    rows = await places.list_all()
    assert {a.place_name for a in rows} == {"p1", "p2"}


@pytest.mark.asyncio
async def test_list_expired_grace(stores):
    auth, places = stores
    u = await auth.create_user(username="a", password="p", role="user")
    await places.acquire("p1", u.id)
    await places.acquire("p2", u.id)
    await places.set_grace("p1", grace_until=10.0)
    await places.set_grace("p2", grace_until=1e12)
    expired = await places.list_expired_grace(now=100.0)
    assert [a.place_name for a in expired] == ["p1"]
