import subprocess

import pytest

from adi_lg_plugins.request import reservation
from adi_lg_plugins.request.errors import BoardUnavailable


def test_parse_token_from_reserve_shell_output():
    out = "export LG_TOKEN=abc123\n"
    assert reservation._parse_token(out) == "abc123"


def test_parse_allocated_place_from_reservations_block():
    # Sample `labgrid-client reservations` output: token header then fields.
    block = (
        "Reservation 'abc123':\n"
        "  owner: ci/runner\n"
        "  state: allocated\n"
        "  filters:\n"
        "    main: daughter-board=ad9361\n"
        "  allocations:\n"
        "    main: lab1/mini2\n"
    )
    assert reservation._parse_allocated_place(block, "abc123") == "mini2"


def test_reserve_and_acquire_happy_path(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        joined = " ".join(cmd)
        if "reserve" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="export LG_TOKEN=tok9\n", stderr="")
        if "reservations" in joined:
            out = "Reservation 'tok9':\n  allocations:\n    main: lab1/mini2\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        if "acquire" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)

    res = reservation.reserve_and_acquire("10.0.0.41:20408", {"daughter-board": "ad9361"}, wait=60)
    assert res.place == "mini2"
    assert res.token == "tok9"
    assert any("acquire" in " ".join(c) for c in calls)


def test_reserve_timeout_raises_board_unavailable(monkeypatch):
    def fake_run(cmd, **kw):
        if "reserve" in " ".join(cmd):
            raise subprocess.TimeoutExpired(cmd, timeout=1)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c", {"daughter-board": "ad9361"}, wait=1)
