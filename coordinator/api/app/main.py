import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.store import AuthStore
from .config import settings
from .grpc_client import CoordinatorClient
from .recorder import Recorder
from .routers import (
    auth,
    catalog,
    console,
    health,
    history,
    places,
    power,
    recordings,
    recovery,
    reservations,
    resources,
    sdmux,
    users,
)
from .ws import router as ws_router

logger = logging.getLogger(__name__)


def make_on_session_dropped(rec_store):
    """Return an on_session_dropped callback that closes the writer and finalizes the recording."""

    async def _on_session_dropped(place, _resource, session):
        rec_id = getattr(session, "recording_id", None)
        writer = getattr(session, "recorder", None)
        if writer is not None:
            try:
                await writer.close()
            except Exception:
                pass
        if rec_id is not None:
            try:
                await rec_store.finish(
                    rec_id,
                    byte_count=getattr(writer, "byte_count", 0),
                    terminated_reason="grace_timeout",
                )
            except Exception as e:
                logger.warning("finalize recording failed: %s", e)

    return _on_session_dropped


@asynccontextmanager
async def lifespan(app: FastAPI):
    recorder = Recorder(settings.database_path)
    await recorder.start()
    app.state.recorder = recorder

    auth_store = AuthStore(settings.database_path)
    app.state.auth_store = auth_store

    from .places.store import PlaceAcquisitionStore

    place_acq_store = PlaceAcquisitionStore(settings.database_path)
    app.state.place_acq_store = place_acq_store

    from .recordings.store import RecordingStore

    rec_store = RecordingStore(settings.database_path)
    app.state.recording_store = rec_store

    from .recordings.retention import run_retention_loop

    retention_task = asyncio.create_task(
        run_retention_loop(
            rec_store,
            retention_days=settings.recording_retention_days,
            max_bytes_per_place=settings.recording_max_bytes_per_place,
        )
    )
    app.state.retention_task = retention_task

    from .console.manager import ConsoleManager

    cmgr = ConsoleManager(grace_seconds=60.0)
    app.state.console_manager = cmgr

    if await auth_store.user_count() == 0:
        await auth_store.create_user(username="analog", password="analog", role="admin")
        app.state.bootstrap_token = None
        logger.warning("=" * 70)
        logger.warning("FIRST RUN: Created default account: analog:analog (admin)")
        logger.warning("=" * 70)
    else:
        app.state.bootstrap_token = None

    from .auth.oidc import OIDCClient

    app.state.oidc = OIDCClient(
        issuer=settings.oidc_issuer_url,
        client_id=settings.oidc_client_id,
        client_secret=settings.oidc_client_secret,
    )

    from .catalog import load_catalog

    app.state.catalog = load_catalog(settings.board_catalog_path)

    client = CoordinatorClient(
        address=settings.coordinator_address,
        name=settings.api_name,
    )
    client.recorder = recorder
    app.state.coordinator = client
    await client.start()

    async def _on_grace_expired(place: str, _resource: str) -> None:
        try:
            await place_acq_store.force_release(place)
            try:
                # We (this gRPC connection) hold the labgrid lock — no
                # fromuser needed; identity is validated by session.
                await client.release_place(place)
            except Exception as e:
                logger.warning("labgrid release on grace expired failed: %s", e)
        except Exception as e:
            logger.warning("on_grace_expired handler failed: %s", e)

    cmgr.on_session_dropped = make_on_session_dropped(rec_store)
    cmgr.on_grace_expired = _on_grace_expired

    # Reconcile: any place labgrid thinks is acquired by an old instance of
    # this API (matches "<hostname>/<api_name>" or just "<api_name>") but
    # has no corresponding row in our DB is stale (orphaned by a previous
    # container restart) — force release on labgrid.
    def _is_our_acquisition(acquired: str | None) -> bool:
        if not acquired:
            return False
        # labgrid usually formats as "<hostname>/<client-name>"; some paths
        # store just the client-name. Match either.
        return acquired == settings.api_name or acquired.endswith("/" + settings.api_name)

    try:
        for place in client.get_places():
            if _is_our_acquisition(place.acquired):
                if await place_acq_store.get(place.name) is None:
                    logger.warning(
                        "Reconcile: releasing orphaned place '%s' (held by '%s')",
                        place.name,
                        place.acquired,
                    )
                    try:
                        await client.release_place(place.name, fromuser=place.acquired)
                    except Exception as e:
                        logger.warning("Reconcile release failed for %s: %s", place.name, e)
    except Exception as e:
        logger.warning("Reconcile loop failed: %s", e)

    yield
    retention_task.cancel()
    try:
        await retention_task
    except asyncio.CancelledError:
        pass
    await client.stop()
    await cmgr.shutdown()
    await recorder.stop()


app = FastAPI(
    title="Labgrid Coordinator Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(places.router, prefix="/api")
app.include_router(resources.router, prefix="/api")
app.include_router(reservations.router, prefix="/api")
app.include_router(ws_router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(console.router, prefix="/api")
app.include_router(recordings.router, prefix="/api")
app.include_router(power.router, prefix="/api")
app.include_router(recovery.router, prefix="/api")
app.include_router(sdmux.router, prefix="/api")
