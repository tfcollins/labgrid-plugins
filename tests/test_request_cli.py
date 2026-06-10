from __future__ import annotations

import signal
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
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


def test_request_flash_mode_without_firmware_errors():
    # flash mode is supported, but requires --firmware.
    result = CliRunner().invoke(cli, ["request", "--part", "ad9371", "--mode", "flash"])
    assert result.exit_code != 0
    assert "firmware" in result.output.lower()


def test_request_flash_mode_passes_firmware_through(monkeypatch):
    lease = _fake_lease(uri=None, place="bq", carrier="zc706")
    fake = _fake_request_yielding(lease)
    monkeypatch.setattr(rc_mod, "request", fake)
    result = CliRunner().invoke(
        cli,
        [
            "request",
            "--part",
            "ad9371",
            "--mode",
            "flash",
            "--firmware",
            "/b/ad9371.elf",
            "--bitstream",
            "/b/sys.bit",
            "--validate",
            "CUSTOM BANNER",
        ],
    )
    assert result.exit_code == 0
    assert fake.kwargs["mode"] == "flash"
    assert fake.kwargs["firmware"] == "/b/ad9371.elf"
    assert fake.kwargs["bitstream"] == "/b/sys.bit"
    assert fake.kwargs["validate"] == "CUSTOM BANNER"


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


def test_install_term_handler_makes_sigterm_raise(monkeypatch):
    installed = {}

    def fake_signal(signum, handler):
        installed[signum] = handler
        return signal.SIG_DFL  # previous handler

    monkeypatch.setattr(rc_mod.signal, "signal", fake_signal)
    rc_mod._install_term_handler()
    handler = installed[signal.SIGTERM]
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)


def test_run_child_terminates_child_on_interrupt(monkeypatch):
    events = []

    class FakeProc:
        def __init__(self):
            self._first = True

        def wait(self, timeout=None):
            if self._first:
                self._first = False
                raise KeyboardInterrupt
            events.append("waited")
            return 0

        def terminate(self):
            events.append("terminated")

        def kill(self):
            events.append("killed")

    monkeypatch.setattr(rc_mod.subprocess, "Popen", lambda *a, **k: FakeProc())
    with pytest.raises(KeyboardInterrupt):
        rc_mod._run_child("sleep 100", {})
    assert "terminated" in events


def test_request_interrupt_releases_and_exits_130(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))

    def interrupt(run_cmd, env):
        raise KeyboardInterrupt

    monkeypatch.setattr(rc_mod, "_run_child", interrupt)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "sleep 100"])
    assert result.exit_code == rc_mod.EXIT_INTERRUPTED


def test_request_no_run_prints_place_when_no_uri(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease(uri=None)))
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    assert result.exit_code == 0
    assert "adrv9002-zcu102" in result.output


def test_request_run_omits_iio_uri_when_none(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease(uri=None)))
    captured = {}

    def fake_run_child(run_cmd, env):
        captured["has_uri"] = "IIO_URI" in env
        captured["place"] = env.get("LG_PLACE")
        return 0

    monkeypatch.setattr(rc_mod, "_run_child", fake_run_child)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert result.exit_code == 0
    assert captured["has_uri"] is False
    assert captured["place"] == "adrv9002-zcu102"


def test_provision_error_emits_boot_failure_annotation_on_gha(monkeypatch):
    err = ProvisionError("boot failed: strategy timeout")
    err.place = "adrv9002-zcu102"

    @contextmanager
    def fake_request(**kwargs):
        raise err
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    assert result.exit_code == EXIT_PROVISION
    assert "::error title=boot-failure::" in result.output
    assert "place=adrv9002-zcu102" in result.output
    assert "part=adrv9002" in result.output


def test_boot_failure_annotation_reason_is_single_line(monkeypatch):
    err = ProvisionError(
        "boot failed: Timeout exceeded.\nbuffer: ::set-env injection\nbefore: junk"
    )
    err.place = "adrv9002-zcu102"

    @contextmanager
    def fake_request(**kwargs):
        raise err
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    annotation_lines = [ln for ln in result.output.splitlines() if ln.startswith("::error")]
    assert len(annotation_lines) == 1
    assert "Timeout exceeded. buffer: ::set-env injection before: junk" in annotation_lines[0]


def test_provision_error_no_annotation_outside_gha(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise ProvisionError("boot failed")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    assert result.exit_code == EXIT_PROVISION
    assert "::error" not in result.output
