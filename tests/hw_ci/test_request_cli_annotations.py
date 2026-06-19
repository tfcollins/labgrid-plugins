from unittest.mock import patch

from click.testing import CliRunner

from adi_lg_plugins.request import BoardUnavailable, NoMatchingBoard
from adi_lg_plugins.tools.request_cli import request_cmd


def _invoke(exc, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with patch("adi_lg_plugins.tools.request_cli.request", side_effect=exc):
        return CliRunner().invoke(request_cmd, ["--part", "ad9081", "--wait", "0"])


def test_no_board_annotation(monkeypatch):
    res = _invoke(NoMatchingBoard("unknown part ad9081"), monkeypatch)
    assert res.exit_code == 10
    assert "::error title=no-board::part=ad9081 reason=unknown part ad9081" in res.output


def test_board_unavailable_annotation(monkeypatch):
    res = _invoke(BoardUnavailable("no free board within 0s"), monkeypatch)
    assert res.exit_code == 11
    assert "::error title=board-unavailable::part=ad9081 reason=no free board within 0s" in res.output


def test_no_annotation_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with patch("adi_lg_plugins.tools.request_cli.request", side_effect=NoMatchingBoard("x")):
        res = CliRunner().invoke(request_cmd, ["--part", "ad9081", "--wait", "0"])
    assert res.exit_code == 10
    assert "::error" not in res.output
