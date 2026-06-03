from __future__ import annotations

import subprocess

import pytest

from adi_lg_plugins.request import reservation
from adi_lg_plugins.request.errors import BoardUnavailable
from adi_lg_plugins.request.reservation import Reservation


def test_filter_args_formats_tags():
    assert reservation._filter_args({"daughter-board": "adrv9002", "carrier": "zcu102"}) == [
        "daughter-board=adrv9002",
        "carrier=zcu102",
    ]


def test_parse_token_extracts_lg_token():
    assert reservation._parse_token("blah\nLG_TOKEN=abc123\nblah") == "abc123"
    assert reservation._parse_token("no token here") is None


def test_parse_allocated_place_finds_place_in_allocations_block():
    out = (
        "Reservation 'abc123':\n"
        "  owner: ci\n"
        "  state: allocated\n"
        "  allocations:\n"
        "    main: lab1-host/adrv9002-zcu102\n"
    )
    assert reservation._parse_allocated_place(out, "abc123") == "adrv9002-zcu102"


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_reserve_and_acquire_happy_path(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(
                stdout="Reservation 'tok9':\n  allocations:\n    main: h/adrv9002-zcu102\n"
            )
        if "acquire" in argv:
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    res = reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert res == Reservation(place="adrv9002-zcu102", token="tok9")


def test_reserve_timeout_raises_board_unavailable(monkeypatch):
    def fake_run(argv, **kw):
        if "reserve" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout"))
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=1)


def test_acquire_failure_cancels_reservation_and_raises(monkeypatch):
    cancelled = []

    def fake_run(argv, **kw):
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(stdout="Reservation 'tok9':\n  allocations:\n    main: h/p1\n")
        if "acquire" in argv:
            return _completed(returncode=1, stderr="busy")
        if "cancel-reservation" in argv:
            cancelled.append(argv)
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert cancelled, "acquire failure must cancel the reservation to avoid a leak"


def test_release_never_raises(monkeypatch):
    def boom(argv, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(reservation.subprocess, "run", boom)
    reservation.release("c:8000", Reservation(place="p1", token="tok9"))


def test_acquire_timeout_cancels_reservation_and_raises(monkeypatch):
    cancelled = []

    def fake_run(argv, **kw):
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(stdout="Reservation 'tok9':\n  allocations:\n    main: h/p1\n")
        if "acquire" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout"))
        if "cancel-reservation" in argv:
            cancelled.append(argv)
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert cancelled, "acquire timeout must cancel the reservation to avoid a leak"


def test_reservations_lookup_timeout_cancels_and_raises(monkeypatch):
    cancelled = []

    def fake_run(argv, **kw):
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout"))
        if "cancel-reservation" in argv:
            cancelled.append(argv)
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert cancelled


def test_unparseable_place_cancels_and_raises(monkeypatch):
    cancelled = []

    def fake_run(argv, **kw):
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(stdout="Reservation 'tok9':\n  (no allocations block)\n")
        if "cancel-reservation" in argv:
            cancelled.append(argv)
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert cancelled, "unparseable allocated place must cancel the reservation to avoid a leak"
