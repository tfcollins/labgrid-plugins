import pytest

from adi_lg_plugins.request import core
from adi_lg_plugins.request.errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
)
from adi_lg_plugins.request.match_client import MatchCandidate, MatchResult
from adi_lg_plugins.request.reservation import Reservation


class FakePlace:
    def __init__(self, name="mini2", carrier="zcu102", strategy="BootFPGASoC"):
        self.name = name
        self.carrier = carrier
        self.daughter_board = "ad9361"
        self.boot_strategy = strategy
        self.hdl_config = None
        self.extra_tags = {}


def _match(satisfiable=True):
    return MatchResult(
        satisfiable=satisfiable,
        reservation_filter={"daughter-board": "ad9361"},
        version="2023_R2_P1",
        matlab_boards={"zcu102": "zynqmp-zcu102-rev10-ad9361-fmcomms2-3"},
        candidates=[MatchCandidate("mini2", "zcu102", False)],
    )


@pytest.fixture
def patched(monkeypatch):
    state = {"released": None, "booted_version": None}

    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match())
    monkeypatch.setattr(
        core.reservation,
        "reserve_and_acquire",
        lambda *a, **k: Reservation(place="mini2", token="tok"),
    )

    def fake_release(coord, res, **k):
        state["released"] = res.place

    monkeypatch.setattr(core.reservation, "release", fake_release)
    monkeypatch.setattr(core, "_concrete_place", lambda coord, name: FakePlace(name=name))
    monkeypatch.setattr(core, "_render_env", lambda place: "/tmp/env.yaml")

    def fake_boot(env_path, strategy, *, version, target_name="main"):
        state["booted_version"] = version
        return object()  # fake target

    monkeypatch.setattr(core, "_boot", fake_boot)
    monkeypatch.setattr(core, "resolve_uri", lambda tg: "ip:10.0.0.57")
    return state


def test_request_yields_lease_and_releases(patched):
    with core.request(part="ad9361") as board:
        assert board.uri == "ip:10.0.0.57"
        assert board.place == "mini2"
        assert board.matlab_board == "zynqmp-zcu102-rev10-ad9361-fmcomms2-3"
        assert board.console is None
    assert patched["released"] == "mini2"
    assert patched["booted_version"] == "2023_R2_P1"


def test_request_releases_on_exception(patched):
    with pytest.raises(RuntimeError):
        with core.request(part="ad9361"):
            raise RuntimeError("boom")
    assert patched["released"] == "mini2"


def test_request_no_match_raises_without_reserving(monkeypatch):
    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match(satisfiable=False))

    def boom(*a, **k):
        raise AssertionError("must not reserve when unsatisfiable")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", boom)
    with pytest.raises(NoMatchingBoard):
        with core.request(part="ad9361"):
            pass


def test_request_flash_mode_not_supported(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="ad9361", mode="flash"):
            pass


def test_request_provision_error_still_releases(patched, monkeypatch):
    def bad_boot(*a, **k):
        raise ProvisionError("boot failed")

    monkeypatch.setattr(core, "_boot", bad_boot)
    with pytest.raises(ProvisionError):
        with core.request(part="ad9361"):
            pass
    assert patched["released"] == "mini2"


def test_request_unavailable_propagates(patched, monkeypatch):
    def busy(*a, **k):
        raise BoardUnavailable("all busy")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", busy)
    with pytest.raises(BoardUnavailable):
        with core.request(part="ad9361"):
            pass


def test_request_unknown_filters_rejected(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="ad9361", hdl_config="lvds"):
            pass
