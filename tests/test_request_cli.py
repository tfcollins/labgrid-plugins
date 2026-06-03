from contextlib import contextmanager
from unittest.mock import MagicMock

from click.testing import CliRunner

from adi_lg_plugins.request.errors import EXIT_NO_MATCH, NoMatchingBoard
from adi_lg_plugins.tools import cli as cli_mod
from adi_lg_plugins.tools.cli import cli


def _runner():
    return CliRunner()


def test_request_help():
    result = _runner().invoke(cli, ["request", "--help"])
    assert result.exit_code == 0
    assert "--part" in result.output


def test_request_flash_mode_rejected():
    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--mode", "flash"])
    assert result.exit_code != 0
    assert "flash" in result.output.lower()


def test_request_runs_command_with_uri(monkeypatch):
    lease = MagicMock(uri="ip:10.0.0.57", place="mini2")

    @contextmanager
    def fake_request(**kwargs):
        yield lease

    captured = {}

    def fake_call(cmd, shell, env):
        captured["cmd"] = cmd
        captured["uri"] = env.get("IIO_URI")
        captured["place"] = env.get("LG_PLACE")
        return 0

    monkeypatch.setattr(cli_mod, "request", fake_request)
    monkeypatch.setattr(cli_mod.subprocess, "call", fake_call)

    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--run", "echo hi"])
    assert result.exit_code == 0
    assert captured["cmd"] == "echo hi"
    assert captured["uri"] == "ip:10.0.0.57"
    assert captured["place"] == "mini2"


def test_request_no_match_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise NoMatchingBoard("no such board")
        yield  # pragma: no cover

    monkeypatch.setattr(cli_mod, "request", fake_request)
    result = _runner().invoke(cli, ["request", "--part", "nope", "--run", "true"])
    assert result.exit_code == EXIT_NO_MATCH


def test_request_propagates_command_exit_code(monkeypatch):
    lease = MagicMock(uri="ip:10.0.0.57", place="mini2")

    @contextmanager
    def fake_request(**kwargs):
        yield lease

    monkeypatch.setattr(cli_mod, "request", fake_request)
    monkeypatch.setattr(cli_mod.subprocess, "call", lambda cmd, shell, env: 3)
    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--run", "false"])
    assert result.exit_code == 3
