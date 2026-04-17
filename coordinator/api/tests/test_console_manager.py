import asyncio

import pytest
import pytest_asyncio

from app.console.manager import ConsoleManager


@pytest_asyncio.fixture
async def echo_server():
    async def handle(reader, writer):
        while True:
            d = await reader.read(4096)
            if not d:
                break
            writer.write(d)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    yield host, port
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_get_or_create_returns_same_session(echo_server):
    host, port = echo_server
    m = ConsoleManager()
    s1 = await m.get_or_create("p", "r", host=host, port=port)
    s2 = await m.get_or_create("p", "r", host=host, port=port)
    assert s1 is s2
    await m.shutdown()


@pytest.mark.asyncio
async def test_drop_session_removes_from_registry(echo_server):
    host, port = echo_server
    m = ConsoleManager()
    s = await m.get_or_create("p", "r", host=host, port=port)
    await m.drop("p", "r")
    assert m._sessions == {}
    assert s.is_closed
    await m.shutdown()


@pytest.mark.asyncio
async def test_grace_timer_drops_after_timeout(echo_server):
    host, port = echo_server
    m = ConsoleManager(grace_seconds=0.1)
    s = await m.get_or_create("p", "r", host=host, port=port)
    expired = asyncio.Event()
    m.on_grace_expired = lambda place, _: expired.set()
    m.arm_grace("p", "r")
    await asyncio.wait_for(expired.wait(), timeout=1.0)
    assert s.is_closed
    await m.shutdown()


@pytest.mark.asyncio
async def test_cancel_grace_keeps_session_alive(echo_server):
    host, port = echo_server
    m = ConsoleManager(grace_seconds=0.5)
    s = await m.get_or_create("p", "r", host=host, port=port)
    m.arm_grace("p", "r")
    m.cancel_grace("p", "r")
    await asyncio.sleep(0.7)
    assert not s.is_closed
    await m.shutdown()


@pytest.mark.asyncio
async def test_on_session_dropped_called_on_grace(echo_server):
    host, port = echo_server
    m = ConsoleManager(grace_seconds=0.1)
    await m.get_or_create("p", "r", host=host, port=port)
    dropped = asyncio.Event()
    m.on_session_dropped = lambda place, resource, session: dropped.set()
    m.arm_grace("p", "r")
    await asyncio.wait_for(dropped.wait(), timeout=1.0)
    await m.shutdown()


@pytest.mark.asyncio
async def test_on_session_dropped_called_on_explicit_drop(echo_server):
    host, port = echo_server
    m = ConsoleManager(grace_seconds=10)
    await m.get_or_create("p", "r", host=host, port=port)
    dropped = asyncio.Event()
    m.on_session_dropped = lambda place, resource, session: dropped.set()
    await m.drop("p", "r")
    assert dropped.is_set()
    await m.shutdown()
