import asyncio

import pytest
import pytest_asyncio

from app.console.session import ConsoleSession


class FakeWS:
    def __init__(self):
        self.sent: list[bytes] = []
        self.in_queue: asyncio.Queue = asyncio.Queue()

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(data)

    async def receive_bytes(self) -> bytes:
        b = await self.in_queue.get()
        if b is None:
            raise RuntimeError("closed")
        return b


@pytest_asyncio.fixture
async def echo_server():
    async def handle(reader, writer):
        while True:
            data = await reader.read(4096)
            if not data:
                break
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    yield host, port
    server.close()
    await server.wait_closed()


@pytest.mark.asyncio
async def test_session_pipes_bytes_both_ways(echo_server):
    host, port = echo_server
    ws = FakeWS()
    session = ConsoleSession(host=host, port=port)
    await session.connect()
    task = asyncio.create_task(session.run(ws))

    await ws.in_queue.put(b"hello")
    await asyncio.sleep(0.1)
    assert b"hello" in b"".join(ws.sent)

    await session.close()
    await task


@pytest.mark.asyncio
async def test_session_close_stops_pipes(echo_server):
    host, port = echo_server
    ws = FakeWS()
    session = ConsoleSession(host=host, port=port)
    await session.connect()
    task = asyncio.create_task(session.run(ws))
    await session.close()
    await asyncio.wait_for(task, timeout=1.0)
    assert session.is_closed


@pytest.mark.asyncio
async def test_connect_unreachable_raises():
    session = ConsoleSession(host="127.0.0.1", port=1)
    with pytest.raises(OSError):
        await session.connect()


class FakeWriter:
    def __init__(self):
        self.output = bytearray()
        self.input = bytearray()

    async def write_output(self, b):
        self.output.extend(b)

    async def write_input(self, b):
        self.input.extend(b)


@pytest.mark.asyncio
async def test_session_tees_to_writer(echo_server):
    host, port = echo_server
    ws = FakeWS()
    writer = FakeWriter()
    session = ConsoleSession(host=host, port=port, recorder=writer)
    await session.connect()
    task = asyncio.create_task(session.run(ws))

    await ws.in_queue.put(b"abc")
    await asyncio.sleep(0.1)
    assert b"abc" in bytes(writer.output)
    assert bytes(writer.input) == b"abc"

    await session.close()
    await task
