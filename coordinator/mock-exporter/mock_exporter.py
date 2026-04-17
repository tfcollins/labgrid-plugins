"""Lightweight mock exporter that registers fake resources with the labgrid
coordinator via the ExporterStream gRPC, without requiring any real hardware.

Usage:
    python mock_exporter.py [-c HOST:PORT] [-n NAME] [RESOURCES_YAML]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
from pathlib import Path
from socket import gethostname

import grpc
import yaml
from labgrid.remote.common import ResourceEntry, queue_as_aiter
from labgrid.remote.generated import labgrid_coordinator_pb2, labgrid_coordinator_pb2_grpc
from labgrid.util import labgrid_version

logger = logging.getLogger(__name__)


class MockExporter:
    """Connects to the coordinator and registers resources from a YAML file."""

    def __init__(self, coordinator: str, name: str, resources_path: str):
        self.coordinator = coordinator
        self.name = name
        self.resources_path = resources_path

        channel_options = [
            ("grpc.keepalive_time_ms", 7500),
            ("grpc.keepalive_timeout_ms", 10000),
            ("grpc.http2.ping_timeout_ms", 10000),
            ("grpc.http2.max_pings_without_data", 0),
        ]
        self.channel = grpc.aio.insecure_channel(target=coordinator, options=channel_options)
        self.stub = labgrid_coordinator_pb2_grpc.CoordinatorStub(self.channel)
        self.out_queue: asyncio.Queue = asyncio.Queue()
        self.groups: dict[str, dict[str, ResourceEntry]] = {}

    def _load_resources(self) -> dict:
        with open(self.resources_path) as f:
            return yaml.safe_load(f)

    async def run(self):
        pump_task = asyncio.create_task(self._message_pump())

        # Send startup
        msg = labgrid_coordinator_pb2.ExporterInMessage()
        msg.startup.version = labgrid_version()
        msg.startup.name = self.name
        self.out_queue.put_nowait(msg)

        # Register all resources
        data = self._load_resources()
        for group_name, resources in data.items():
            group = self.groups.setdefault(group_name, {})
            for resource_name, params in resources.items():
                if params is None:
                    continue
                cls = params.pop("cls", resource_name)
                config = {
                    "avail": True,
                    "cls": cls,
                    "params": params,
                }
                entry = ResourceEntry(config)
                group[resource_name] = entry

                # Send resource to coordinator
                res_msg = labgrid_coordinator_pb2.ExporterInMessage()
                res_pb2 = entry.as_pb2()
                res_msg.resource.CopyFrom(res_pb2)
                res_msg.resource.path.group_name = group_name
                res_msg.resource.path.resource_name = resource_name
                self.out_queue.put_nowait(res_msg)
                logger.info("Registered %s/%s (%s)", group_name, resource_name, cls)

        logger.info("All resources registered. Waiting...")

        # Wait for pump to finish (runs until coordinator disconnects or signal)
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        await stop_event.wait()
        self.out_queue.put_nowait(None)
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        await self.channel.close()

    async def _message_pump(self):
        try:
            async for out_msg in self.stub.ExporterStream(queue_as_aiter(self.out_queue)):
                kind = out_msg.WhichOneof("kind")
                if kind == "hello":
                    logger.info("Connected to coordinator version %s", out_msg.hello.version)
                elif kind == "set_acquired_request":
                    req = out_msg.set_acquired_request
                    group_name = req.group_name
                    resource_name = req.resource_name
                    place_name = req.place_name if req.HasField("place_name") else None
                    logger.info(
                        "Acquire request: %s/%s -> %s",
                        group_name,
                        resource_name,
                        place_name,
                    )
                    # Respond with success
                    resp = labgrid_coordinator_pb2.ExporterInMessage()
                    resp.response.success = True
                    self.out_queue.put_nowait(resp)

                    # Update resource acquired state
                    group = self.groups.get(group_name, {})
                    entry = group.get(resource_name)
                    if entry:
                        if place_name:
                            entry.acquire(place_name)
                        else:
                            entry.release()
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                logger.error("Coordinator unavailable: %s", e.details())
            else:
                logger.exception("gRPC error in mock exporter")
        except asyncio.CancelledError:
            pass


async def amain(args):
    exporter = MockExporter(
        coordinator=args.coordinator,
        name=args.name,
        resources_path=args.resources,
    )
    await exporter.run()


def main():
    parser = argparse.ArgumentParser(description="Mock labgrid exporter for testing")
    parser.add_argument(
        "-c",
        "--coordinator",
        type=str,
        default=os.environ.get("LG_COORDINATOR", "127.0.0.1:20408"),
        help="Coordinator host:port (default: LG_COORDINATOR env or 127.0.0.1:20408)",
    )
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=os.environ.get("LG_EXPORTER_NAME", f"mock-{gethostname()}"),
        help="Exporter name (default: mock-<hostname>)",
    )
    parser.add_argument(
        "resources",
        nargs="?",
        default=str(Path(__file__).parent / "resources.yaml"),
        help="Resources YAML file (default: resources.yaml next to this script)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
