import os
import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch
from adi_lg_plugins.tools.cli import cli

@pytest.fixture
def runner():
    return CliRunner()

def test_cli_help(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "ADI Labgrid Plugins CLI" in result.output

def test_boot_fabric_help(runner):
    result = runner.invoke(cli, ["boot-fabric", "--help"])
    assert result.exit_code == 0
    assert "Boot FPGA Fabric strategy" in result.output

@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_fabric_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        with open("test.bit", "w") as f:
            f.write("dummy")
        
        result = runner.invoke(cli, ["boot-fabric", "-c", "config.yaml", "--bitstream", "test.bit"])
        
        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_env.assert_called_once_with("config.yaml")
        mock_resource.bitstream_path = os.path.abspath("test.bit")
        mock_strat.transition.assert_called_with("shell")

@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_soc_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        
        result = runner.invoke(cli, ["boot-soc", "-c", "config.yaml", "--release", "2023_R2"])
        
        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_resource.release_version = "2023_R2"
        mock_strat.transition.assert_called_with("shell")

@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_soc_ssh_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_resource = MagicMock()
    mock_tg.get_resource.return_value = mock_resource
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        
        result = runner.invoke(cli, ["boot-soc-ssh", "-c", "config.yaml", "--release", "2023_R2"])
        
        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        mock_resource.release_version = "2023_R2"
        mock_strat.transition.assert_called_with("shell")

@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_selmap_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        with open("local.bin", "w") as f:
            f.write("dummy")
        
        result = runner.invoke(cli, [
            "boot-selmap", "-c", "config.yaml", 
            "--pre-boot-file", "local.bin:/boot/remote.bin"
        ])
        
        assert result.exit_code == 0
        assert "Successfully reached shell!" in result.output
        assert mock_strat.pre_boot_boot_files == {os.path.abspath("local.bin"): "/boot/remote.bin"}
        mock_strat.transition.assert_called_with("shell")

@patch("adi_lg_plugins.tools.cli.Environment")
def test_boot_fabric_failure(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat
    mock_strat.transition.side_effect = Exception("Hardware timeout")

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
        
        result = runner.invoke(cli, ["boot-fabric", "-c", "config.yaml"])
        
        assert result.exit_code != 0
        assert "Transition failed: Hardware timeout" in result.output
