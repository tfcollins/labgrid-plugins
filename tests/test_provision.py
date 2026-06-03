from __future__ import annotations

from contextlib import contextmanager

import pytest

from adi_lg_plugins.request import provision as provision_mod
from adi_lg_plugins.request.errors import NoBoardSource
from adi_lg_plugins.request.provision import provision_or_reuse


def test_reuse_path_yields_uri_without_self_requesting(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("must not self-request when a URI is provided")

    monkeypatch.setattr(provision_mod, "request", boom)
    with provision_or_reuse("adrv9002", "zcu102", uri="ip:10.0.0.9") as lease:
        assert lease.uri == "ip:10.0.0.9"
        assert lease.place == ""  # externally provided
        assert lease.carrier == "zcu102"


def test_uri_wins_when_both_uri_and_part_given(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("uri must win; no self-request")

    monkeypatch.setattr(provision_mod, "request", boom)
    with provision_or_reuse("adrv9002", uri="ip:1.2.3.4") as lease:
        assert lease.uri == "ip:1.2.3.4"


def test_request_path_enters_request_and_releases(monkeypatch):
    released = {"v": False}
    sentinel = object()

    @contextmanager
    def fake_request(**kwargs):
        fake_request.kwargs = kwargs
        try:
            yield sentinel
        finally:
            released["v"] = True

    monkeypatch.setattr(provision_mod, "request", fake_request)
    with provision_or_reuse("adrv9002", "zcu102", coord="c:8000", bootfile="2023_R2_P1") as lease:
        assert lease is sentinel
        assert released["v"] is False  # not released until exit
    assert released["v"] is True
    assert fake_request.kwargs == {
        "part": "adrv9002",
        "carrier": "zcu102",
        "bootfile": "2023_R2_P1",
        "coord": "c:8000",
    }


def test_neither_source_raises_no_board_source():
    with pytest.raises(NoBoardSource):
        with provision_or_reuse(None, None):
            pass  # pragma: no cover
