from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from click.testing import CliRunner

from adi_lg_plugins.request import BoardUnavailable, NoMatchingBoard, ProvisionError
from adi_lg_plugins.request.errors import EXIT_NO_MATCH, EXIT_PROVISION, EXIT_UNAVAILABLE
from adi_lg_plugins.tools import request_cli as rc_mod
from adi_lg_plugins.tools.cli import cli


def _fake_lease(uri="ip:10.0.0.57", place="adrv9002-zcu102", carrier="zcu102"):
    return MagicMock(uri=uri, place=place, carrier=carrier)


def _fake_request_yielding(lease):
    @contextmanager
    def fake_request(**kwargs):
        fake_request.kwargs = kwargs
        yield lease

    return fake_request


def test_request_registered_and_help():
    result = CliRunner().invoke(cli, ["request", "--help"])
    assert result.exit_code == 0
    assert "--part" in result.output
    assert "--power-down" in result.output


def test_request_flash_mode_rejected():
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--mode", "flash"])
    assert result.exit_code != 0
    assert "flash" in result.output.lower()


def test_request_no_run_prints_uri(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    assert result.exit_code == 0
    assert "ip:10.0.0.57" in result.output


def test_request_runs_command_with_exported_env(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    captured = {}

    def fake_run_child(run_cmd, env):
        captured["cmd"] = run_cmd
        captured["uri"] = env.get("IIO_URI")
        captured["place"] = env.get("LG_PLACE")
        captured["carrier"] = env.get("LG_CARRIER")
        return 0

    monkeypatch.setattr(rc_mod, "_run_child", fake_run_child)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "echo hi"])
    assert result.exit_code == 0
    assert captured == {
        "cmd": "echo hi",
        "uri": "ip:10.0.0.57",
        "place": "adrv9002-zcu102",
        "carrier": "zcu102",
    }


def test_request_propagates_child_exit_code(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    monkeypatch.setattr(rc_mod, "_run_child", lambda c, e: 3)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "false"])
    assert result.exit_code == 3


def test_request_power_down_flag_passed(monkeypatch):
    fake = _fake_request_yielding(_fake_lease())
    monkeypatch.setattr(rc_mod, "request", fake)
    monkeypatch.setattr(rc_mod, "_run_child", lambda c, e: 0)

    CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--power-down", "--run", "true"])
    assert fake.kwargs["power_down"] is True

    CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert fake.kwargs["power_down"] is False


def test_request_no_match_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise NoMatchingBoard("no such board")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "nope", "--run", "true"])
    assert result.exit_code == EXIT_NO_MATCH


def test_request_unavailable_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise BoardUnavailable("all busy")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert result.exit_code == EXIT_UNAVAILABLE


def test_request_provision_error_exit_code_and_tail(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise ProvisionError("boot failed", console_tail="kernel panic xyz")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert result.exit_code == EXIT_PROVISION
    assert "kernel panic xyz" in result.output
