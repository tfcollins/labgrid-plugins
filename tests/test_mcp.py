import asyncio
from unittest.mock import MagicMock, patch

from adi_lg_plugins.tools.mcp import _boot_fabric, _boot_selmap, _boot_soc, mcp


def test_mcp_registration():
    """Verify that tools are registered with the FastMCP server."""
    tools = asyncio.run(mcp.get_tools())
    # If tools is a dict, keys are tool names. If it's a list of strings, same.
    assert "boot_fabric" in tools
    assert "boot_soc" in tools
    assert "boot_soc_ssh" in tools
    assert "boot_selmap" in tools


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_fabric_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_get.return_value = (mock_tg, mock_strat)

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_fabric(str(config), target="main", state="shell")

    assert "Successfully reached state 'shell'" in result
    mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_soc_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_get.return_value = (mock_tg, mock_strat)

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_soc(str(config), release_version="2023_R2", state="booted")

    assert "Successfully reached state 'booted'" in result
    mock_strat.transition.assert_called_with("booted")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_selmap_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_get.return_value = (mock_tg, mock_strat)

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_selmap(str(config), pre_boot_files={"local.bin": "/boot/remote.bin"})

    assert "Successfully reached state 'shell'" in result
    assert mock_strat.pre_boot_boot_files is not None
    mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_mcp_error_handling(mock_get, tmp_path):
    mock_get.side_effect = Exception("Environment error")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_fabric(str(config))
    assert "Error during BootFabric transition: Environment error" in result
