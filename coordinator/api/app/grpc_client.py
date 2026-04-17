"""gRPC client that connects to the labgrid coordinator and maintains a cached
view of all places and resources via the bidirectional ClientStream."""

from __future__ import annotations

import asyncio
import itertools
import logging
from collections.abc import Callable
from socket import gethostname
from typing import Any

import grpc
from labgrid.remote.common import (
    Place,
    ReservationState,
    ResourceEntry,
    queue_as_aiter,
)
from labgrid.remote.generated import labgrid_coordinator_pb2, labgrid_coordinator_pb2_grpc
from labgrid.util import labgrid_version

from .models import (
    ExporterModel,
    PlaceModel,
    ReservationFilterModel,
    ReservationModel,
    ResourceMatchModel,
    ResourceModel,
)

logger = logging.getLogger(__name__)


def _place_to_model(place: Place) -> PlaceModel:
    d = place.asdict()
    return PlaceModel(
        name=place.name,
        aliases=d["aliases"],
        comment=d["comment"],
        tags=d["tags"],
        matches=[
            ResourceMatchModel(
                exporter=m.exporter,
                group=m.group,
                cls=m.cls,
                name=m.name,
                rename=m.rename,
            )
            for m in place.matches
        ],
        acquired=d["acquired"],
        acquired_resources=d["acquired_resources"],
        allowed=d["allowed"],
        created=d["created"],
        changed=d["changed"],
        reservation=d["reservation"],
    )


def _resource_to_model(exporter: str, group: str, name: str, entry: ResourceEntry) -> ResourceModel:
    return ResourceModel(
        exporter=exporter,
        group=group,
        cls=entry.cls,
        name=name,
        params=entry.params,
        acquired=entry.acquired,
        avail=entry.avail,
    )


def _reservation_from_pb2(pb2) -> ReservationModel:
    state_name = ReservationState(pb2.state).name
    filters = {}
    for k, v in pb2.filters.items():
        filters[k] = ReservationFilterModel(filter=dict(v.filter))
    return ReservationModel(
        owner=pb2.owner,
        token=pb2.token,
        state=state_name,
        prio=pb2.prio,
        filters=filters,
        allocations=dict(pb2.allocations),
        created=pb2.created,
        timeout=pb2.timeout,
    )


class CoordinatorClient:
    """Maintains a live connection to the labgrid coordinator via gRPC,
    caching all place and resource state for fast REST API reads."""

    def __init__(self, address: str, name: str = "web-dashboard"):
        self.address = address
        self.name = name

        # gRPC channel options matching labgrid's defaults
        channel_options = [
            ("grpc.keepalive_time_ms", 7500),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.http2.ping_timeout_ms", 10000),
            ("grpc.http2.max_pings_without_data", 0),
        ]
        self.channel = grpc.aio.insecure_channel(
            target=address,
            options=channel_options,
        )
        self.stub = labgrid_coordinator_pb2_grpc.CoordinatorStub(self.channel)

        # Cached state
        self._places: dict[str, Place] = {}
        self._resources: dict[str, dict[str, dict[str, ResourceEntry]]] = {}

        # Stream machinery
        self._out_queue: asyncio.Queue = asyncio.Queue()
        self._pump_task: asyncio.Task | None = None
        self._sync_id = itertools.count(start=1)
        self._sync_events: dict[int, asyncio.Event] = {}
        self._stopping = asyncio.Event()

        # Callback for WebSocket broadcasting
        self.on_update: Callable[[dict], None] | None = None
        self.recorder: Any | None = None

    @property
    def connected(self) -> bool:
        return self._pump_task is not None and not self._stopping.is_set()

    async def start(self):
        """Open the ClientStream and subscribe to all places and resources."""
        self._pump_task = asyncio.create_task(self._message_pump())

        # Send startup + subscribe messages
        msg = labgrid_coordinator_pb2.ClientInMessage()
        msg.startup.version = labgrid_version()
        msg.startup.name = f"{gethostname()}/{self.name}"
        self._out_queue.put_nowait(msg)

        msg = labgrid_coordinator_pb2.ClientInMessage()
        msg.subscribe.all_places = True
        self._out_queue.put_nowait(msg)

        msg = labgrid_coordinator_pb2.ClientInMessage()
        msg.subscribe.all_resources = True
        self._out_queue.put_nowait(msg)

        await self._sync_with_coordinator()
        if self._stopping.is_set():
            logger.error("Could not connect to coordinator at %s", self.address)
        else:
            logger.info("Connected to coordinator at %s", self.address)

    async def stop(self):
        """Gracefully close the stream and channel."""
        self._out_queue.put_nowait(None)
        if self._pump_task:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
        await self.channel.close()

    async def _sync_with_coordinator(self):
        identifier = next(self._sync_id)
        event = self._sync_events[identifier] = asyncio.Event()
        msg = labgrid_coordinator_pb2.ClientInMessage()
        msg.sync.id = identifier
        self._out_queue.put_nowait(msg)
        await event.wait()

    async def _message_pump(self):
        got_message = False
        try:
            call = self.stub.ClientStream(queue_as_aiter(self._out_queue))
            async for out_msg in call:
                got_message = True
                for update in out_msg.updates:
                    kind = update.WhichOneof("kind")
                    if kind == "resource":
                        res = update.resource
                        data = ResourceEntry.data_from_pb2(res)
                        self._on_resource_changed(
                            res.path.exporter_name,
                            res.path.group_name,
                            res.path.resource_name,
                            data,
                        )
                    elif kind == "del_resource":
                        path = update.del_resource
                        self._on_resource_changed(
                            path.exporter_name, path.group_name, path.resource_name, {}
                        )
                    elif kind == "place":
                        self._on_place_changed(update.place)
                    elif kind == "del_place":
                        self._on_place_deleted(update.del_place)

                if out_msg.HasField("sync"):
                    event = self._sync_events.pop(out_msg.sync.id, None)
                    if event:
                        event.set()
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                if got_message:
                    logger.error("Coordinator became unavailable: %s", e.details())
                else:
                    logger.error("Coordinator is unavailable: %s", e.details())
            else:
                logger.exception("Unexpected gRPC error in message pump")
        except Exception:
            logger.exception("Error in message pump")
        finally:
            self._stopping.set()
            self._out_queue.put_nowait(None)
            # Cancel all pending syncs
            for event in self._sync_events.values():
                event.set()
            self._sync_events.clear()

    def _record(self, *args, **kwargs):
        if self.recorder is None:
            return
        asyncio.ensure_future(self.recorder.record_event(*args, **kwargs))

    def _on_resource_changed(self, exporter: str, group: str, name: str, data: dict):
        resource_key = f"{exporter}/{group}/{data.get('cls', '?')}/{name}"

        if not data or "cls" not in data:
            ## Delete event. Don't materialize empty parents — a delete for an
            ## exporter/group we've never seen must stay a no-op (prevents the
            ## ghost-exporter-with-zero-resources symptom on the dashboard).
            group_dict = self._resources.get(exporter, {}).get(group)
            if not group_dict or name not in group_dict:
                return
            group_dict.pop(name)
            ## Cascade-prune empty parents so a depopulated exporter disappears.
            if not group_dict:
                self._resources[exporter].pop(group, None)
                if not self._resources[exporter]:
                    self._resources.pop(exporter, None)
            self._record("resource_offline", resource_key=resource_key)
            if self.on_update:
                self.on_update(
                    {
                        "type": "resource_delete",
                        "data": {"exporter": exporter, "group": group, "name": name},
                    }
                )
            return

        group_dict = self._resources.setdefault(exporter, {}).setdefault(group, {})
        if name not in group_dict:
            group_dict[name] = ResourceEntry(data)
            resource_key = f"{exporter}/{group}/{data['cls']}/{name}"
            if data.get("avail"):
                self._record("resource_online", resource_key=resource_key)
            else:
                self._record("resource_offline", resource_key=resource_key)
            if self.on_update:
                self.on_update(
                    {
                        "type": "resource_update",
                        "data": _resource_to_model(
                            exporter, group, name, group_dict[name]
                        ).model_dump(),
                    }
                )
        else:
            old_avail = group_dict[name].avail
            old_acquired = group_dict[name].acquired
            group_dict[name].data = data
            new_avail = group_dict[name].avail
            new_acquired = group_dict[name].acquired
            resource_key = f"{exporter}/{group}/{group_dict[name].cls}/{name}"

            if not old_avail and new_avail:
                self._record("resource_online", resource_key=resource_key)
            elif old_avail and not new_avail:
                self._record("resource_offline", resource_key=resource_key)
            if old_acquired is None and new_acquired is not None:
                self._record("resource_acquired", resource_key=resource_key, user=new_acquired)
            elif old_acquired is not None and new_acquired is None:
                self._record("resource_released", resource_key=resource_key)

            if self.on_update:
                self.on_update(
                    {
                        "type": "resource_update",
                        "data": _resource_to_model(
                            exporter, group, name, group_dict[name]
                        ).model_dump(),
                    }
                )

    def _on_place_changed(self, place_pb2):
        name = place_pb2.name
        old_acquired = None
        is_new = name not in self._places

        if not is_new:
            old_acquired = self._places[name].acquired
            self._places[name].update_from_pb2(place_pb2)
        else:
            self._places[name] = Place.from_pb2(place_pb2)

        place = self._places[name]
        new_acquired = place.acquired

        if is_new:
            self._record("place_created", place_name=name)
        if old_acquired is None and new_acquired is not None:
            self._record("place_acquired", place_name=name, user=new_acquired)
        elif old_acquired is not None and new_acquired is None:
            self._record("place_released", place_name=name, user=old_acquired)

        if self.on_update:
            self.on_update({"type": "place_update", "data": _place_to_model(place).model_dump()})

    def _on_place_deleted(self, name: str):
        self._places.pop(name, None)
        self._record("place_deleted", place_name=name)
        if self.on_update:
            self.on_update({"type": "place_delete", "data": {"name": name}})

    # --- Read operations (from cache) ---

    def get_places(self) -> list[PlaceModel]:
        return [_place_to_model(p) for p in self._places.values()]

    def get_place(self, name: str) -> PlaceModel | None:
        place = self._places.get(name)
        return _place_to_model(place) if place else None

    def get_resource(self, place_name: str, resource_name: str) -> ResourceModel | None:
        place = self.get_place(place_name)
        if place is None:
            return None
        for m in place.matches:
            for r in self.get_resources():
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
        results = []
        for exp_name, groups in self._resources.items():
            if exporter_filter and exp_name != exporter_filter:
                continue
            for grp_name, resources in groups.items():
                for res_name, entry in resources.items():
                    if cls_filter and entry.cls != cls_filter:
                        continue
                    if avail_filter is not None and entry.avail != avail_filter:
                        continue
                    results.append(_resource_to_model(exp_name, grp_name, res_name, entry))
        return results

    def get_exporters(self) -> list[ExporterModel]:
        exporters = []
        for exp_name, groups in self._resources.items():
            grp_models: dict[str, list[ResourceModel]] = {}
            for grp_name, resources in groups.items():
                grp_models[grp_name] = [
                    _resource_to_model(exp_name, grp_name, res_name, entry)
                    for res_name, entry in resources.items()
                ]
            exporters.append(ExporterModel(name=exp_name, groups=grp_models))
        return exporters

    # --- Write operations (unary RPCs) ---

    async def add_place(self, name: str):
        await self.stub.AddPlace(labgrid_coordinator_pb2.AddPlaceRequest(name=name))
        await self._sync_with_coordinator()

    async def delete_place(self, name: str):
        await self.stub.DeletePlace(labgrid_coordinator_pb2.DeletePlaceRequest(name=name))
        await self._sync_with_coordinator()

    async def acquire_place(self, name: str):
        await self.stub.AcquirePlace(labgrid_coordinator_pb2.AcquirePlaceRequest(placename=name))
        await self._sync_with_coordinator()

    async def release_place(self, name: str, fromuser: str | None = None):
        req = labgrid_coordinator_pb2.ReleasePlaceRequest(placename=name)
        if fromuser:
            req.fromuser = fromuser
        await self.stub.ReleasePlace(req)
        await self._sync_with_coordinator()

    async def set_place_tags(self, name: str, tags: dict[str, str]):
        await self.stub.SetPlaceTags(
            labgrid_coordinator_pb2.SetPlaceTagsRequest(placename=name, tags=tags)
        )
        await self._sync_with_coordinator()

    async def set_place_comment(self, name: str, comment: str):
        await self.stub.SetPlaceComment(
            labgrid_coordinator_pb2.SetPlaceCommentRequest(placename=name, comment=comment)
        )
        await self._sync_with_coordinator()

    async def add_place_match(self, name: str, pattern: str, rename: str | None = None):
        req = labgrid_coordinator_pb2.AddPlaceMatchRequest(placename=name, pattern=pattern)
        if rename:
            req.rename = rename
        await self.stub.AddPlaceMatch(req)
        await self._sync_with_coordinator()

    async def delete_place_match(self, name: str, pattern: str, rename: str | None = None):
        req = labgrid_coordinator_pb2.DeletePlaceMatchRequest(placename=name, pattern=pattern)
        if rename:
            req.rename = rename
        await self.stub.DeletePlaceMatch(req)
        await self._sync_with_coordinator()

    async def add_place_alias(self, name: str, alias: str):
        await self.stub.AddPlaceAlias(
            labgrid_coordinator_pb2.AddPlaceAliasRequest(placename=name, alias=alias)
        )
        await self._sync_with_coordinator()

    async def delete_place_alias(self, name: str, alias: str):
        await self.stub.DeletePlaceAlias(
            labgrid_coordinator_pb2.DeletePlaceAliasRequest(placename=name, alias=alias)
        )
        await self._sync_with_coordinator()

    async def allow_place(self, name: str, user: str):
        await self.stub.AllowPlace(
            labgrid_coordinator_pb2.AllowPlaceRequest(placename=name, user=user)
        )
        await self._sync_with_coordinator()

    async def create_reservation(
        self, filters: dict[str, dict[str, str]], prio: float = 0.0
    ) -> ReservationModel:
        pb2_filters = {}
        for k, v in filters.items():
            f = labgrid_coordinator_pb2.Reservation.Filter()
            for fk, fv in v.items():
                f.filter[fk] = fv
            pb2_filters[k] = f
        resp = await self.stub.CreateReservation(
            labgrid_coordinator_pb2.CreateReservationRequest(filters=pb2_filters, prio=prio)
        )
        return _reservation_from_pb2(resp.reservation)

    async def cancel_reservation(self, token: str):
        await self.stub.CancelReservation(
            labgrid_coordinator_pb2.CancelReservationRequest(token=token)
        )

    async def poll_reservation(self, token: str) -> ReservationModel:
        resp = await self.stub.PollReservation(
            labgrid_coordinator_pb2.PollReservationRequest(token=token)
        )
        return _reservation_from_pb2(resp.reservation)

    async def get_reservations(self) -> list[ReservationModel]:
        resp = await self.stub.GetReservations(labgrid_coordinator_pb2.GetReservationsRequest())
        return [_reservation_from_pb2(r) for r in resp.reservations]
