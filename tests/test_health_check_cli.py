"""Unit tests for the adi-lg health-check CLI command."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from adi_lg_plugins.tools.cli import cli
from adi_lg_plugins.tools.health_check_cli import (
    EXIT_BUSY,
    EXIT_NOT_FOUND,
    EXIT_SUCCESS,
    HealthCheckResult,
)


@pytest.fixture
def runner():
    return CliRunner()


def test_health_check_help(runner):
    result = runner.invoke(cli, ["health-check", "--help"])
    assert result.exit_code == 0
    assert "Run an automated boot health check on a deployed board" in result.output


@patch("adi_lg_plugins.tools.health_check_cli.run_health_check")
def test_health_check_passed(mock_run, runner):
    mock_run.return_value = HealthCheckResult(
        place="mini2",
        status="passed",
        boot_strategy="BootFPGASoC",
        image="2023_R2_P1",
        ip_address="192.168.1.102",
        iiod_reachable=True,
        duration=25.4,
        uname="Linux analog 5.15.0 #1 SMP",
    )

    result = runner.invoke(cli, ["health-check", "-p", "mini2"])
    assert result.exit_code == EXIT_SUCCESS
    assert "Health check passed for 'mini2'" in result.output
    assert "192.168.1.102" in result.output
    assert "Linux analog" in result.output


@patch("adi_lg_plugins.tools.health_check_cli.run_health_check")
def test_health_check_json_output(mock_run, runner):
    mock_run.return_value = HealthCheckResult(
        place="mini2",
        status="passed",
        boot_strategy="BootFPGASoC",
        image="2023_R2_P1",
        ip_address="192.168.1.102",
        iiod_reachable=True,
        duration=25.4,
    )

    result = runner.invoke(cli, ["health-check", "-p", "mini2", "--json"])
    assert result.exit_code == EXIT_SUCCESS
    data = json.loads(result.output)
    assert data["place"] == "mini2"
    assert data["status"] == "passed"
    assert data["iiod_reachable"] is True


@patch("adi_lg_plugins.tools.health_check_cli.run_health_check")
def test_health_check_busy(mock_run, runner):
    mock_run.return_value = HealthCheckResult(
        place="mini2",
        status="busy",
        error_message="Place 'mini2' is currently acquired",
        duration=0.5,
    )

    result = runner.invoke(cli, ["health-check", "-p", "mini2"])
    assert result.exit_code == EXIT_BUSY
    assert "is busy" in result.output


@patch("adi_lg_plugins.tools.health_check_cli.run_health_check")
def test_health_check_not_found(mock_run, runner):
    mock_run.return_value = HealthCheckResult(
        place="nonexistent",
        status="error",
        error_message="Place 'nonexistent' not found",
        duration=0.2,
    )

    result = runner.invoke(cli, ["health-check", "-p", "nonexistent"])
    assert result.exit_code == EXIT_NOT_FOUND
    assert "Error: Place 'nonexistent' not found" in result.output
