"""Coordinator REST→CLI fallback behaviour."""

from __future__ import annotations

import http.client
import json

import pytest

from adi_lg_plugins.hw_ci import coordinator as coord_mod

_FAKE_CLI_PAYLOAD = [
    {
        "name": "mini2",
        "tags": {
            "carrier": "zcu102",
            "daughter-board": "ad9081",
            "boot-strategy": "BootFPGASoC",
        },
        "acquired": None,
    }
]


@pytest.fixture
def _stub_cli(monkeypatch):
    calls: list[tuple] = []

    def _stub(coord: str, timeout: float = 15.0) -> list[dict]:
        calls.append((coord, timeout))
        return list(_FAKE_CLI_PAYLOAD)

    monkeypatch.setattr(coord_mod, "_fetch_places_cli", _stub)
    return calls


@pytest.mark.parametrize(
    "rest_exc",
    [
        http.client.BadStatusLine("garbled \x00\x01\x02"),
        ConnectionRefusedError("refused"),
        TimeoutError("timed out"),
        json.JSONDecodeError("not json", "x", 0),
        ValueError("malformed payload"),
    ],
    ids=["bad_status_line", "connect_refused", "socket_timeout", "json_decode", "value_error"],
)
def test_fetch_raw_places_falls_back_on_rest_failure(monkeypatch, _stub_cli, rest_exc):
    def _raise(*args, **kwargs):
        raise rest_exc

    monkeypatch.setattr(coord_mod, "_fetch_places_rest", _raise)

    out = coord_mod.fetch_raw_places("10.0.0.41:20408")

    assert out == _FAKE_CLI_PAYLOAD
    assert _stub_cli == [("10.0.0.41:20408", 15.0)]


def test_fetch_raw_places_force_cli_skips_rest(monkeypatch, _stub_cli):
    def _boom(*args, **kwargs):
        raise AssertionError("REST path must not be tried when force_cli=True")

    monkeypatch.setattr(coord_mod, "_fetch_places_rest", _boom)

    out = coord_mod.fetch_raw_places("10.0.0.41:20408", force_cli=True)

    assert out == _FAKE_CLI_PAYLOAD
    assert _stub_cli == [("10.0.0.41:20408", 15.0)]


def test_fetch_raw_places_rest_success_path(monkeypatch, _stub_cli):
    """When REST returns clean JSON, CLI is never invoked. The REST call
    targets the API port (host:8000), not the gRPC coordinator port."""
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    rest_payload = [{"name": "rest-only", "tags": {}, "acquired": None}]

    def _ok(coord, timeout=15.0):
        assert coord == "10.0.0.41:8000"
        return rest_payload

    monkeypatch.setattr(coord_mod, "_fetch_places_rest", _ok)

    out = coord_mod.fetch_raw_places("10.0.0.41:20408")

    assert out == rest_payload
    assert _stub_cli == []


def test_resolve_coordinator_port_validation(monkeypatch):
    # Valid coordinator addresses:
    assert coord_mod.resolve_coordinator("10.0.0.41:20408") == "10.0.0.41:20408"
    assert coord_mod.resolve_coordinator("10.0.0.41") == "10.0.0.41"
    assert coord_mod.resolve_coordinator("[::1]:20408") == "[::1]:20408"
    assert coord_mod.resolve_coordinator("tcp://10.0.0.41:20408") == "tcp://10.0.0.41:20408"

    # Invalid coordinator addresses (port out of range):
    with pytest.raises(ValueError, match="Port out of range 0-65535"):
        coord_mod.resolve_coordinator("10.0.0.41:204008")

    # Invalid coordinator addresses (non-integer port):
    with pytest.raises(ValueError, match="Port could not be cast to integer value"):
        coord_mod.resolve_coordinator("10.0.0.41:20408abc")


def test_resolve_coordinator_env_port_validation(monkeypatch):
    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:204008")
    with pytest.raises(ValueError, match="Port out of range 0-65535"):
        coord_mod.resolve_coordinator(None)
