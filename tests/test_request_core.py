from __future__ import annotations

import pytest

from adi_lg_plugins.request import core
from adi_lg_plugins.request.errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
)
from adi_lg_plugins.request.match_client import MatchResult
from adi_lg_plugins.request.reservation import Reservation

# ── _resolve_api unit tests ───────────────────────────────────────────────────


def test_resolve_api_derives_host_port_8000():
    """Coordinator at host:20408 → REST API at host:8000."""
    assert core._resolve_api("10.0.0.41:20408") == "10.0.0.41:8000"


def test_resolve_api_no_port_uses_8000():
    """Coordinator with no port → still host:8000."""
    assert core._resolve_api("mycoord") == "mycoord:8000"


def test_resolve_api_strips_scheme():
    """Coordinator with grpc:// scheme → still host:8000."""
    assert core._resolve_api("grpc://10.0.0.41:20408") == "10.0.0.41:8000"


def test_resolve_api_honors_adi_lg_api_override(monkeypatch):
    """ADI_LG_API env var overrides the derived address."""
    monkeypatch.setenv("ADI_LG_API", "192.168.1.99:9000")
    assert core._resolve_api("10.0.0.41:20408") == "192.168.1.99:9000"


def test_resolve_api_honors_lg_api_override(monkeypatch):
    """LG_API env var overrides the derived address."""
    monkeypatch.setenv("LG_API", "staging.example.com:8080")
    assert core._resolve_api("10.0.0.41:20408") == "staging.example.com:8080"


class FakePlace:
    def __init__(self, name="adrv9002-zcu102"):
        self.name = name
        self.carrier = "zcu102"
        self.daughter_board = "adrv9002"
        self.boot_strategy = "BootFPGASoC"
        self.hdl_config = None
        self.extra_tags = {}


def _match(satisfiable=True):
    return MatchResult(
        satisfiable=satisfiable,
        reason="" if satisfiable else "unknown part",
        reservation_filter={"daughter-board": "adrv9002", "carrier": "zcu102"},
        image="2023_R2_P1",
        strategy="BootFPGASoC",
        place="adrv9002-zcu102",
    )


@pytest.fixture
def patched(monkeypatch):
    state = {
        "released": None,
        "booted_image": None,
        "powered_off": None,
        "cleaned": None,
        "get_match_coord": None,
        "reserve_coord": None,
    }

    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "10.0.0.41:20408")

    def fake_get_match(coord, **k):
        state["get_match_coord"] = coord
        return _match()

    monkeypatch.setattr(core.match_client, "get_match", fake_get_match)

    def fake_reserve(coord, *a, **k):
        state["reserve_coord"] = coord
        return Reservation(place="adrv9002-zcu102", token="tok")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", fake_reserve)
    monkeypatch.setattr(
        core.reservation, "release", lambda coord, res, **k: state.update(released=res.place)
    )
    monkeypatch.setattr(core, "_concrete_place", lambda coord, name: FakePlace(name=name))
    monkeypatch.setattr(core, "_render_env", lambda place: "/tmp/env.yaml")

    def fake_boot(env_path, strategy, *, image, target_name="main"):
        state["booted_image"] = image
        return object()  # fake labgrid target

    monkeypatch.setattr(core, "_boot", fake_boot)
    monkeypatch.setattr(core, "resolve_uri", lambda tg: "ip:10.0.0.57")
    monkeypatch.setattr(core, "_power_off", lambda tg, strat: state.update(powered_off=strat))
    monkeypatch.setattr(core, "_cleanup_target", lambda tg: state.update(cleaned=True))
    return state


def test_request_yields_lease_and_releases(patched):
    with core.request(part="adrv9002") as board:
        assert board.uri == "ip:10.0.0.57"
        assert board.place == "adrv9002-zcu102"
        assert board.carrier == "zcu102"
        assert board.tags["daughter-board"] == "adrv9002"
        assert board.console is None
    assert patched["released"] == "adrv9002-zcu102"
    assert patched["booted_image"] == "2023_R2_P1"
    assert patched["powered_off"] is None  # power_down defaults off
    assert patched["cleaned"] is True


def test_request_releases_on_exception(patched):
    with pytest.raises(RuntimeError):
        with core.request(part="adrv9002"):
            raise RuntimeError("boom")
    assert patched["released"] == "adrv9002-zcu102"


def test_request_power_down_powers_off_before_release(patched):
    with core.request(part="adrv9002", power_down=True):
        pass
    assert patched["powered_off"] == "BootFPGASoC"
    assert patched["released"] == "adrv9002-zcu102"


def test_request_no_match_raises_without_reserving(monkeypatch):
    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match(satisfiable=False))

    def boom(*a, **k):
        raise AssertionError("must not reserve when unsatisfiable")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", boom)
    with pytest.raises(NoMatchingBoard):
        with core.request(part="adrv9002"):
            pass


def test_request_provision_error_still_releases(patched, monkeypatch):
    def bad_boot(*a, **k):
        raise ProvisionError("boot failed")

    monkeypatch.setattr(core, "_boot", bad_boot)
    with pytest.raises(ProvisionError):
        with core.request(part="adrv9002"):
            pass
    assert patched["released"] == "adrv9002-zcu102"


def test_request_unavailable_propagates(patched, monkeypatch):
    def busy(*a, **k):
        raise BoardUnavailable("all busy")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", busy)
    with pytest.raises(BoardUnavailable):
        with core.request(part="adrv9002"):
            pass
    assert patched["released"] is None  # nothing acquired -> nothing released


def test_request_flash_mode_not_supported(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="adrv9002", mode="flash"):
            pass


def test_request_unknown_filters_rejected(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="adrv9002", hdl_config="lvds"):
            pass


def test_request_concrete_place_failure_still_releases(patched, monkeypatch):
    def boom(coord, name):
        from adi_lg_plugins.request.errors import ProvisionError

        raise ProvisionError("place vanished")

    monkeypatch.setattr(core, "_concrete_place", boom)
    with pytest.raises(ProvisionError):
        with core.request(part="adrv9002"):
            pass
    assert patched["released"] == "adrv9002-zcu102"
    assert patched["cleaned"] is None  # no target -> no cleanup
    assert patched["powered_off"] is None


def test_request_resolve_uri_failure_still_cleans_and_releases(patched, monkeypatch):
    def boom(tg):
        from adi_lg_plugins.request.errors import ProvisionError

        raise ProvisionError("no NetworkService")

    monkeypatch.setattr(core, "resolve_uri", boom)
    with pytest.raises(ProvisionError):
        with core.request(part="adrv9002"):
            pass
    assert patched["cleaned"] is True  # boot succeeded -> target exists -> cleaned
    assert patched["released"] == "adrv9002-zcu102"


# ── REST API vs gRPC coordinator split (Bug 3) ───────────────────────────────


def test_request_get_match_uses_rest_api_addr(patched):
    """get_match must receive the REST API address (host:8000), not the gRPC coord."""
    with core.request(part="adrv9002"):
        pass
    # resolve_coordinator returns "10.0.0.41:20408"; REST API must be "10.0.0.41:8000"
    assert patched["get_match_coord"] == "10.0.0.41:8000"


def test_request_reserve_uses_grpc_coord(patched):
    """reserve_and_acquire must receive the gRPC coordinator address, not the REST API."""
    with core.request(part="adrv9002"):
        pass
    assert patched["reserve_coord"] == "10.0.0.41:20408"
