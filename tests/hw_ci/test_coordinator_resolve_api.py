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
