import asyncio
import threading
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.store import AuthStore
from app.console.manager import ConsoleManager
from app.models import ResourceModel
from app.places.store import PlaceAcquisitionStore
from app.recorder import Recorder
from app.recordings.store import RecordingStore


@pytest.fixture
def echo_server():
    """Start an asyncio echo server in a background thread."""
    started = threading.Event()
    holder = {}
    loop_holder = {}

    def run():
        loop = asyncio.new_event_loop()
        loop_holder["loop"] = loop
        asyncio.set_event_loop(loop)

        async def handle(reader, writer):
            while True:
                d = await reader.read(4096)
                if not d:
                    break
                writer.write(d)
                await writer.drain()
            writer.close()

        async def main():
            srv = await asyncio.start_server(handle, "127.0.0.1", 0)
            holder["host"], holder["port"] = srv.sockets[0].getsockname()[:2]
            holder["server"] = srv
            started.set()
            try:
                async with srv:
                    await srv.serve_forever()
            except asyncio.CancelledError:
                pass

        try:
            loop.run_until_complete(main())
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    started.wait(2.0)
    yield holder["host"], holder["port"]
    try:
        loop_holder["loop"].call_soon_threadsafe(holder["server"].close)
    except Exception:
        pass


@pytest.fixture
def console_app(tmp_path, echo_server, mock_client_with_data):
    from app.config import settings as _cfg
    from app.main import app, make_on_session_dropped

    db = str(tmp_path / "h.db")
    loop = asyncio.new_event_loop()
    rec = Recorder(db)
    loop.run_until_complete(rec.start())
    auth = AuthStore(db)
    pacq = PlaceAcquisitionStore(db)
    rec_store = RecordingStore(db)
    cmgr = ConsoleManager(grace_seconds=0.2)
    cmgr.on_session_dropped = make_on_session_dropped(rec_store)

    # Point recordings_dir at a writable tmp location
    _orig_recordings_dir = _cfg.recordings_dir
    _cfg.recordings_dir = str(tmp_path / "recordings")

    host, port = echo_server
    # Add a NetworkSerialPort resource and matching match on the place
    mock_client_with_data._resources.append(
        ResourceModel(
            exporter="lab1-host",
            group="VCU118_AD9081",
            cls="NetworkSerialPort",
            name="NetworkSerialPort",
            params={"host": host, "port": port},
            avail=True,
        )
    )
    # Ensure the place's match covers cls="*" (already does in fixture).

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.coordinator = mock_client_with_data
        _app.state.recorder = rec
        _app.state.auth_store = auth
        _app.state.place_acq_store = pacq
        _app.state.console_manager = cmgr
        _app.state.recording_store = rec_store
        _app.state.bootstrap_token = None
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:

        def login(username, role="user"):
            loop.run_until_complete(auth.create_user(username=username, password="pw", role=role))
            c.post("/api/auth/login", json={"username": username, "password": "pw"})

        c.login = login
        c.loop = loop
        c.acq_store = pacq
        c.cmgr = cmgr
        c.rec_store = rec_store
        yield c
    app.router.lifespan_context = original
    _cfg.recordings_dir = _orig_recordings_dir
    loop.run_until_complete(cmgr.shutdown())
    loop.run_until_complete(rec.stop())
    loop.close()


def test_ws_unauthenticated_rejected(console_app):
    c = console_app
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/places/vcu118-lab1/resources/NetworkSerialPort/console"):
            pass


def test_ws_non_owner_rejected(console_app):
    c = console_app
    c.login("alice")
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/api/places/vcu118-lab1/resources/NetworkSerialPort/console"):
            pass


def test_ws_owner_can_connect_and_echo(console_app):
    c = console_app
    c.login("alice")
    # Lookup alice in auth store
    from app.auth.store import AuthStore as _AS

    alice = c.loop.run_until_complete(_AS(c.acq_store.db_path).get_user_by_username("alice"))
    c.loop.run_until_complete(c.acq_store.acquire("vcu118-lab1", alice.id))

    with c.websocket_connect("/api/places/vcu118-lab1/resources/NetworkSerialPort/console") as ws:
        ws.send_bytes(b"hello")
        import time

        time.sleep(0.1)
        data = ws.receive_bytes()
        assert b"hello" in data


def test_owner_session_creates_and_finalizes_recording(console_app):
    c = console_app
    c.login("alice")
    from app.auth.store import AuthStore as _AS

    alice = c.loop.run_until_complete(_AS(c.acq_store.db_path).get_user_by_username("alice"))
    c.loop.run_until_complete(c.acq_store.acquire("vcu118-lab1", alice.id))

    with c.websocket_connect("/api/places/vcu118-lab1/resources/NetworkSerialPort/console") as ws:
        ws.send_bytes(b"hi")
        import time

        time.sleep(0.1)
        ws.receive_bytes()

    # Allow grace to fire (fixture grace=0.2s)
    import time as _t

    _t.sleep(0.5)

    recs = c.loop.run_until_complete(c.rec_store.list())
    assert len(recs) >= 1
    rec = recs[0]
    assert rec.place_name == "vcu118-lab1"
    assert rec.resource_name == "NetworkSerialPort"
    assert rec.byte_count > 0
    assert rec.ended_at is not None
    assert rec.terminated_reason == "grace_timeout"
