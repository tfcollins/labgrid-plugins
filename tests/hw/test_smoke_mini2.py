"""Smoke test against the 'mini2' real lab place.

Validates the full HW-CI pipeline against real hardware:
  - reusable workflow's preflight discovered the coordinator place
  - acquire-place composite reserved + acquired the place
  - the labgrid env yaml resolves against the real exporter
  - the NetworkService resource published by the live exporter on mini2
    advertises an IP address (i.e. the board exporter is alive)

Deliberately minimal — no SD flashing, no boot transition. Those are
separate (and heavier) tests that need the kuiper / mass-storage stack.

Local invocation:
    pytest -v --run-hardware --lg-env tests/hw/env_mini2_smoke.yaml \
        tests/hw/test_smoke_mini2.py
"""

from __future__ import annotations

import socket

import pytest

pytestmark = pytest.mark.hardware


def test_env_resolves(target):
    """The labgrid env loads and yields a target — exporter is alive."""
    assert target is not None
    assert target.resources, "target has no resources published by the exporter"


def test_network_service_advertised(target):
    """The exporter publishes a NetworkService with a real address."""
    ns = target.get_resource("NetworkService")
    assert ns is not None, "no NetworkService resource on the place"
    assert ns.address, f"NetworkService has empty address: {ns!r}"


def test_network_service_reachable(target):
    """The advertised address answers on its port (TCP connect within 5s)."""
    ns = target.get_resource("NetworkService")
    addr = ns.address
    # NetworkService model carries the port via `params.port` or defaults
    # to 22 (the conventional SSH for labgrid). Fall back to 22 if missing.
    port = getattr(ns, "port", 22) or 22
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5.0)
    try:
        sock.connect((addr, port))
    finally:
        sock.close()
