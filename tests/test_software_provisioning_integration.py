import os
import pytest
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from adi_lg_plugins.tools.cli import cli

@pytest.fixture
def runner():
    return CliRunner()

@patch("adi_lg_plugins.tools.cli.Environment")
def test_provision_software_success(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat
    
    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")
            
        result = runner.invoke(cli, [
            "provision-software", 
            "-c", "config.yaml",
            "--package", "htop",
            "--repo", "https://github.com/foo.git,/tmp/foo,dev",
            "--build", "make,/tmp/foo",
            "--test", "pytest,/tmp/foo"
        ])
        
        assert result.exit_code == 0
        assert "Successfully reached tested!" in result.output
        
        mock_env.assert_called_with("config.yaml")
        assert mock_strat.packages == ["htop"]
        assert mock_strat.repos == [{"url": "https://github.com/foo.git", "dest": "/tmp/foo", "branch": "dev"}]
        assert mock_strat.build_steps == [{"cmd": "make", "dir": "/tmp/foo"}]
        assert mock_strat.test_steps == [{"cmd": "pytest", "dir": "/tmp/foo"}]
        
        mock_strat.transition.assert_called_with("tested")

@patch("adi_lg_plugins.tools.cli.Environment")
def test_provision_software_fail(mock_env, runner):
    mock_tg = MagicMock()
    mock_env.return_value.get_target.return_value = mock_tg
    mock_strat = MagicMock()
    mock_tg.get_driver.return_value = mock_strat
    mock_strat.transition.side_effect = Exception("Build failed")

    with runner.isolated_filesystem():
        with open("config.yaml", "w") as f:
            f.write("targets: {main: {}}")

        result = runner.invoke(cli, ["provision-software", "-c", "config.yaml"])

        assert result.exit_code != 0
        assert "Provisioning failed: Build failed" in result.output