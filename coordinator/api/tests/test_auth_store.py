import pytest
import pytest_asyncio

from app.auth.store import AuthStore, User
from app.recorder import Recorder


@pytest_asyncio.fixture
async def store(tmp_path):
    db = str(tmp_path / "h.db")
    r = Recorder(db)
    await r.start()
    s = AuthStore(db)
    yield s
    await r.stop()


@pytest.mark.asyncio
async def test_create_and_get_user(store):
    u = await store.create_user(username="alice", password="pw1", role="admin")
    assert isinstance(u, User)
    assert u.id > 0
    assert u.username == "alice"
    assert u.role == "admin"
    assert u.password_hash is not None
    got = await store.get_user_by_username("alice")
    assert got.id == u.id


@pytest.mark.asyncio
async def test_username_unique(store):
    await store.create_user(username="bob", password="pw", role="user")
    with pytest.raises(ValueError, match="exists"):
        await store.create_user(username="bob", password="pw", role="user")


@pytest.mark.asyncio
async def test_list_users(store):
    await store.create_user(username="a", password="p", role="user")
    await store.create_user(username="b", password="p", role="admin")
    users = await store.list_users()
    assert {u.username for u in users} == {"a", "b"}


@pytest.mark.asyncio
async def test_delete_user(store):
    u = await store.create_user(username="x", password="p", role="user")
    await store.delete_user(u.id)
    assert await store.get_user_by_username("x") is None


@pytest.mark.asyncio
async def test_set_password(store):
    u = await store.create_user(username="p", password="old", role="user")
    await store.set_password(u.id, "new")
    fresh = await store.get_user_by_id(u.id)
    from app.auth.passwords import verify_password

    assert verify_password("new", fresh.password_hash)
    assert not verify_password("old", fresh.password_hash)


@pytest.mark.asyncio
async def test_set_role(store):
    u = await store.create_user(username="r", password="p", role="user")
    await store.set_role(u.id, "admin")
    fresh = await store.get_user_by_id(u.id)
    assert fresh.role == "admin"


@pytest.mark.asyncio
async def test_set_disabled(store):
    u = await store.create_user(username="d", password="p", role="user")
    await store.set_disabled(u.id, True)
    fresh = await store.get_user_by_id(u.id)
    assert fresh.disabled_at is not None
    await store.set_disabled(u.id, False)
    fresh = await store.get_user_by_id(u.id)
    assert fresh.disabled_at is None


@pytest.mark.asyncio
async def test_user_count(store):
    assert await store.user_count() == 0
    await store.create_user(username="a", password="p", role="user")
    assert await store.user_count() == 1


@pytest.mark.asyncio
async def test_create_and_resolve_session(store):
    u = await store.create_user(username="s", password="p", role="user")
    sid = await store.create_session(u.id, ttl_seconds=60)
    assert isinstance(sid, str)
    assert len(sid) >= 32
    resolved = await store.resolve_session(sid)
    assert resolved.id == u.id


@pytest.mark.asyncio
async def test_resolve_session_unknown_returns_none(store):
    assert await store.resolve_session("nope") is None


@pytest.mark.asyncio
async def test_resolve_session_expired_returns_none(store):
    u = await store.create_user(username="e", password="p", role="user")
    sid = await store.create_session(u.id, ttl_seconds=-1)
    assert await store.resolve_session(sid) is None


@pytest.mark.asyncio
async def test_resolve_session_disabled_user_returns_none(store):
    u = await store.create_user(username="x", password="p", role="user")
    sid = await store.create_session(u.id, ttl_seconds=60)
    await store.set_disabled(u.id, True)
    assert await store.resolve_session(sid) is None


@pytest.mark.asyncio
async def test_delete_session(store):
    u = await store.create_user(username="d", password="p", role="user")
    sid = await store.create_session(u.id, ttl_seconds=60)
    await store.delete_session(sid)
    assert await store.resolve_session(sid) is None


@pytest.mark.asyncio
async def test_purge_expired_sessions(store):
    u = await store.create_user(username="p", password="p", role="user")
    expired = await store.create_session(u.id, ttl_seconds=-1)
    fresh = await store.create_session(u.id, ttl_seconds=60)
    n = await store.purge_expired_sessions()
    assert n == 1
    assert await store.resolve_session(expired) is None
    assert await store.resolve_session(fresh) is not None
