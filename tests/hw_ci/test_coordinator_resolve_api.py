from adi_lg_plugins.hw_ci import coordinator as coord_mod
from adi_lg_plugins.hw_ci.coordinator import _resolve_api


def test_derives_api_port_8000_from_grpc_coordinator(monkeypatch):
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    assert _resolve_api("10.0.0.41:20408") == "10.0.0.41:8000"


def test_strips_scheme_then_derives_port(monkeypatch):
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    assert _resolve_api("http://coord.lab:20408") == "coord.lab:8000"


def test_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("ADI_LG_API", "api.lab:9001")
    assert _resolve_api("10.0.0.41:20408") == "api.lab:9001"


def test_request_core_reexports_same_callable():
    from adi_lg_plugins.request.core import _resolve_api as core_resolve

    assert core_resolve is _resolve_api


# ── fetch_raw_places must hit the REST port, not the gRPC port ────────────────


def _capture_rest(monkeypatch):
    seen = {}

    def fake_rest(coord, timeout=15.0):
        seen["coord"] = coord
        return [{"name": "x", "tags": {}, "acquired": None}]

    monkeypatch.setattr(coord_mod, "_fetch_places_rest", fake_rest)
    return seen


def test_fetch_raw_places_queries_rest_api_port(monkeypatch):
    """fetch_raw_places("host:20408") must GET host:8000/api/places, not the
    gRPC port (which returns garbled BadStatusLine on every machine)."""
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    seen = _capture_rest(monkeypatch)
    out = coord_mod.fetch_raw_places("10.0.0.41:20408")
    assert seen["coord"] == "10.0.0.41:8000"
    assert out[0]["name"] == "x"


def test_fetch_raw_places_rest_honors_lg_api_override(monkeypatch):
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.setenv("LG_API", "api.lab:9001")
    seen = _capture_rest(monkeypatch)
    coord_mod.fetch_raw_places("10.0.0.41:20408")
    assert seen["coord"] == "api.lab:9001"


def test_warn_if_rest_port_warns_on_8000(capsys):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    warn_if_rest_port("10.0.0.41:8000")
    assert "REST port :8000" in capsys.readouterr().err


def test_warn_if_rest_port_silent_on_grpc(capsys):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    warn_if_rest_port("10.0.0.41:20408")
    assert capsys.readouterr().err == ""


def test_warn_if_rest_port_github_annotation(capsys, monkeypatch):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    warn_if_rest_port("http://host:8000")
    assert capsys.readouterr().err.startswith("::warning::")
