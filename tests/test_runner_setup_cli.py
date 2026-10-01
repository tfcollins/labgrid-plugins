from click.testing import CliRunner

from adi_lg_plugins.hw_ci.cli import main as hw_ci_main
from adi_lg_plugins.tools.cli import cli
from adi_lg_plugins.tools.runner_setup.cli import setup_runner_cmd


def test_setup_runner_help():
    runner = CliRunner()
    result = runner.invoke(setup_runner_cmd, ["--help"])
    assert result.exit_code == 0
    assert "Setup, configure, and service a GitHub Actions hardware runner" in result.output
    assert "--mode" in result.output
    assert "--scope" in result.output
    assert "--coord" in result.output
    assert "--env-file" in result.output


def test_setup_runner_check_only():
    runner = CliRunner()
    result = runner.invoke(setup_runner_cmd, ["--check-only", "--mode", "exporter"])
    assert "Prerequisites Check" in result.output
    assert "Python version" in result.output


def test_setup_runner_non_interactive_missing_mode():
    runner = CliRunner()
    result = runner.invoke(setup_runner_cmd, ["--non-interactive"])
    assert result.exit_code != 0
    assert "--mode" in result.output


def test_setup_runner_non_interactive_missing_scope():
    runner = CliRunner()
    result = runner.invoke(setup_runner_cmd, ["--non-interactive", "--mode", "exporter"])
    assert result.exit_code != 0
    assert "--scope" in result.output


def test_setup_runner_dry_run_exporter():
    runner = CliRunner()
    result = runner.invoke(
        setup_runner_cmd,
        [
            "--mode",
            "exporter",
            "--scope",
            "repo:analogdevicesinc/labgrid-plugins",
            "--coord",
            "10.0.0.41:20408",
            "--token",
            "TEST_TOKEN",
            "--non-interactive",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN ACTIVE" in result.output
    assert "repo:analogdevicesinc/labgrid-plugins" in result.output
    assert "10.0.0.41:20408" in result.output
    assert "Dry-run complete" in result.output


def test_setup_runner_dry_run_direct(tmp_path):
    runner = CliRunner()
    dummy_env = tmp_path / "env.yaml"
    dummy_env.write_text("targets: {}\n")

    result = runner.invoke(
        setup_runner_cmd,
        [
            "--mode",
            "direct",
            "--scope",
            "repo:analogdevicesinc/labgrid-plugins",
            "--env-file",
            str(dummy_env),
            "--token",
            "TEST_TOKEN",
            "--non-interactive",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "DRY RUN ACTIVE" in result.output
    assert "direct" in result.output
    assert str(dummy_env) in result.output


def test_adi_lg_cli_integration():
    runner = CliRunner()
    result = runner.invoke(cli, ["setup-runner", "--help"])
    assert result.exit_code == 0
    assert "Setup, configure, and service a GitHub Actions hardware runner" in result.output

    alias_res = runner.invoke(cli, ["runner-setup", "--help"])
    assert alias_res.exit_code == 0


def test_hw_ci_cli_integration():
    from io import StringIO
    from unittest.mock import patch

    with patch("sys.stdout", new_callable=StringIO) as mock_out:
        try:
            hw_ci_main(["setup-runner", "--help"])
        except SystemExit as e:
            assert e.code == 0
        assert (
            "setup and configure a self-hosted GitHub Actions hardware runner"
            in mock_out.getvalue()
        )
