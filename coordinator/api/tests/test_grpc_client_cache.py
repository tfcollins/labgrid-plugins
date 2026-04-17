"""Unit tests for CoordinatorClient's cached-resource bookkeeping.

The gRPC stream pushes individual resource-change events. These tests verify
that the cache stays consistent under add/remove sequences — in particular,
that an exporter whose resources have all been removed disappears from
`get_exporters()`, rather than lingering as a zero-resource ghost.
"""

from __future__ import annotations

import asyncio

from app.grpc_client import CoordinatorClient


def _make_client() -> CoordinatorClient:
    ## Construct inside an event loop so grpc.aio.insecure_channel has one
    ## to attach to. The channel is lazy; no connection is made.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return CoordinatorClient(address="127.0.0.1:0")


def _add(client: CoordinatorClient, exporter: str, group: str, name: str, cls: str):
    client._on_resource_changed(
        exporter,
        group,
        name,
        {"cls": cls, "params": {}, "acquired": None, "avail": True},
    )


def _remove(client: CoordinatorClient, exporter: str, group: str, name: str):
    client._on_resource_changed(exporter, group, name, {})


def test_exporter_dropped_after_last_resource_removed():
    client = _make_client()
    _add(client, "bq", "tlab", "NetworkService", "NetworkService")

    assert [e.name for e in client.get_exporters()] == ["bq"]

    _remove(client, "bq", "tlab", "NetworkService")

    assert client.get_exporters() == []


def test_group_pruned_when_last_resource_removed():
    client = _make_client()
    _add(client, "lab1", "GROUP_A", "r1", "NetworkService")
    _add(client, "lab1", "GROUP_B", "r2", "NetworkService")

    _remove(client, "lab1", "GROUP_A", "r1")

    exporters = client.get_exporters()
    assert len(exporters) == 1
    assert exporters[0].name == "lab1"
    assert list(exporters[0].groups.keys()) == ["GROUP_B"]


def test_other_exporters_survive_when_one_goes_empty():
    client = _make_client()
    _add(client, "mini2", "tlab", "NetworkService", "NetworkService")
    _add(client, "bq", "tlab", "NetworkService", "NetworkService")

    _remove(client, "bq", "tlab", "NetworkService")

    assert [e.name for e in client.get_exporters()] == ["mini2"]


def test_delete_event_for_unknown_resource_is_noop():
    """Coordinator may replay delete events at subscribe time. A delete for
    an exporter/group/name we have never seen must not create a ghost entry."""
    client = _make_client()

    _remove(client, "never-seen", "tlab", "Something")

    assert client.get_exporters() == []
