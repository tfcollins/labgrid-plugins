"""Test fixtures with a mocked CoordinatorClient that requires no gRPC connection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.models import (
    ExporterModel,
    PlaceModel,
    ReservationFilterModel,
    ReservationModel,
    ResourceMatchModel,
    ResourceModel,
)


@pytest.fixture(autouse=True, scope="session")
def disable_secure_cookie():
    """Disable secure-only cookie flag so TestClient (HTTP) can send session cookies."""
    original = settings.session_cookie_secure
    settings.session_cookie_secure = False
    yield
    settings.session_cookie_secure = original


class MockCoordinatorClient:
    """In-memory mock of CoordinatorClient for unit testing routers."""

    def __init__(self):
        self.address = "mock:20408"
        self.on_update = None
        self._connected = True
        self._places: dict[str, PlaceModel] = {}
        self._resources: list[ResourceModel] = []
        self._reservations: list[ReservationModel] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def get_places(self) -> list[PlaceModel]:
        return list(self._places.values())

    def get_place(self, name: str) -> PlaceModel | None:
        return self._places.get(name)

    def get_resource(self, place_name: str, resource_name: str):
        place = self.get_place(place_name)
        if place is None:
            return None
        for m in place.matches:
            for r in self._resources:
                if r.exporter == m.exporter and r.group == m.group:
                    final_name = m.rename or r.name
                    if final_name == resource_name:
                        return r
        return None

    def get_resources(
        self,
        exporter_filter: str | None = None,
        cls_filter: str | None = None,
        avail_filter: bool | None = None,
    ) -> list[ResourceModel]:
        results = self._resources
        if exporter_filter:
            results = [r for r in results if r.exporter == exporter_filter]
        if cls_filter:
            results = [r for r in results if r.cls == cls_filter]
        if avail_filter is not None:
            results = [r for r in results if r.avail == avail_filter]
        return results

    def get_exporters(self) -> list[ExporterModel]:
        by_exporter: dict[str, dict[str, list[ResourceModel]]] = {}
        for r in self._resources:
            by_exporter.setdefault(r.exporter, {}).setdefault(r.group, []).append(r)
        return [ExporterModel(name=name, groups=groups) for name, groups in by_exporter.items()]

    async def add_place(self, name: str):
        self._places[name] = PlaceModel(name=name)

    async def delete_place(self, name: str):
        self._places.pop(name, None)

    async def acquire_place(self, name: str):
        if name in self._places:
            self._places[name].acquired = "test-user"

    async def release_place(self, name: str, fromuser: str | None = None):
        if name in self._places:
            self._places[name].acquired = None

    async def allow_place(self, name: str, user: str):
        pass

    async def set_place_tags(self, name: str, tags: dict[str, str]):
        if name in self._places:
            self._places[name].tags = tags

    async def set_place_comment(self, name: str, comment: str):
        if name in self._places:
            self._places[name].comment = comment

    async def add_place_match(self, name: str, pattern: str, rename: str | None = None):
        if name in self._places:
            parts = pattern.split("/")
            match = ResourceMatchModel(
                exporter=parts[0],
                group=parts[1],
                cls=parts[2],
                name=parts[3] if len(parts) > 3 else None,
                rename=rename,
            )
            self._places[name].matches.append(match)

    async def delete_place_match(self, name: str, pattern: str, rename: str | None = None):
        pass

    async def create_reservation(
        self, filters: dict[str, dict[str, str]], prio: float = 0.0
    ) -> ReservationModel:
        r = ReservationModel(
            owner="test-user",
            token="ABCDEF1234",
            state="waiting",
            prio=prio,
            filters={k: ReservationFilterModel(filter=v) for k, v in filters.items()},
        )
        self._reservations.append(r)
        return r

    async def cancel_reservation(self, token: str):
        self._reservations = [r for r in self._reservations if r.token != token]

    async def poll_reservation(self, token: str) -> ReservationModel:
        for r in self._reservations:
            if r.token == token:
                return r
        raise Exception(f"Reservation {token} not found")

    async def get_reservations(self) -> list[ReservationModel]:
        return self._reservations


@pytest.fixture
def mock_client():
    return MockCoordinatorClient()


@pytest.fixture
def mock_client_with_data(mock_client):
    """Pre-populated mock client with sample places and resources."""
    mock_client._places["vcu118-lab1"] = PlaceModel(
        name="vcu118-lab1",
        tags={"board": "vcu118", "chip": "ad9081"},
        matches=[ResourceMatchModel(exporter="lab1-host", group="VCU118_AD9081", cls="*")],
    )
    mock_client._places["rpi-lab1"] = PlaceModel(
        name="rpi-lab1",
        acquired="alice",
        tags={"board": "rpi"},
    )
    mock_client._resources = [
        ResourceModel(
            exporter="lab1-host",
            group="VCU118_AD9081",
            cls="NetworkService",
            name="NetworkService",
            params={"address": "10.0.0.23", "username": "root"},
            avail=True,
        ),
        ResourceModel(
            exporter="lab1-host",
            group="VCU118_AD9081",
            cls="RawSerialPort",
            name="RawSerialPort",
            params={"port": "/dev/ttyUSB1", "speed": 115200},
            avail=True,
        ),
        ResourceModel(
            exporter="lab1-host",
            group="RPI_CM4",
            cls="NetworkService",
            name="NetworkService",
            params={"address": "10.0.0.149"},
            avail=False,
        ),
    ]
    return mock_client


@pytest.fixture
def client_with_recorder(tmp_path):
    """FastAPI TestClient with a real Recorder backed by a temp SQLite DB."""
    import asyncio
    from contextlib import asynccontextmanager

    from app.main import app
    from app.recorder import Recorder

    db_path = str(tmp_path / "test_history.db")
    recorder = Recorder(db_path)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(recorder.start())

    # Override lifespan to avoid connecting to a real gRPC coordinator
    @asynccontextmanager
    async def _test_lifespan(_app):
        _app.state.coordinator = MockCoordinatorClient()
        _app.state.recorder = recorder
        yield

    original_router_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _test_lifespan

    with TestClient(app) as client:
        yield client

    app.router.lifespan_context = original_router_lifespan
    loop.run_until_complete(recorder.stop())
    loop.close()


@pytest.fixture
def client(mock_client, tmp_path):
    """FastAPI TestClient with mocked coordinator."""
    import asyncio

    from app.auth.store import AuthStore
    from app.main import app
    from app.places.store import PlaceAcquisitionStore
    from app.recorder import Recorder

    db = str(tmp_path / "h.db")
    rec = Recorder(db)
    asyncio.new_event_loop().run_until_complete(rec.start())
    app.state.coordinator = mock_client
    app.state.recorder = rec
    app.state.auth_store = AuthStore(db)
    app.state.place_acq_store = PlaceAcquisitionStore(db)
    return TestClient(app)


@pytest.fixture
def client_with_data(mock_client_with_data, tmp_path):
    """FastAPI TestClient with pre-populated mock data."""
    import asyncio

    from app.auth.store import AuthStore
    from app.main import app
    from app.places.store import PlaceAcquisitionStore
    from app.recorder import Recorder

    db = str(tmp_path / "h.db")
    rec = Recorder(db)
    asyncio.new_event_loop().run_until_complete(rec.start())
    app.state.coordinator = mock_client_with_data
    app.state.recorder = rec
    app.state.auth_store = AuthStore(db)
    app.state.place_acq_store = PlaceAcquisitionStore(db)
    return TestClient(app)


@pytest.fixture
def authed_lifespan_client(tmp_path, mock_client_with_data):
    """TestClient with mock coordinator + real AuthStore. Provides login helpers."""
    import asyncio
    from contextlib import asynccontextmanager

    from app.auth.store import AuthStore
    from app.main import app
    from app.recorder import Recorder

    db = str(tmp_path / "h.db")
    loop = asyncio.new_event_loop()
    rec = Recorder(db)
    loop.run_until_complete(rec.start())
    store = AuthStore(db)

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.coordinator = mock_client_with_data
        _app.state.recorder = rec
        _app.state.auth_store = store
        _app.state.bootstrap_token = None
        from app.places.store import PlaceAcquisitionStore

        _app.state.place_acq_store = PlaceAcquisitionStore(db)
        yield

    original = app.router.lifespan_context
    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:

        def login(username: str, role: str = "user"):
            loop.run_until_complete(store.create_user(username=username, password="pw", role=role))
            c.post("/api/auth/login", json={"username": username, "password": "pw"})

        c.login = login
        yield c
    app.router.lifespan_context = original
    loop.run_until_complete(rec.stop())
    loop.close()
