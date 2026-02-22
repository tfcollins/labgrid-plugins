import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from adi_lg_plugins.tools.mcp import (
    _run_strategy,
    boot_fabric,
    boot_selmap,
    boot_soc,
    boot_soc_ssh,
    boot_soc_tftp,
    get_session_info,
    list_sessions,
    mcp,
    provision_software,
    run_shell_command,
    run_ssh_command,
    resource_list_sessions,
    resource_session_info,
)


@pytest.mark.asyncio
async def test_mcp_registration():
    """Verify that tools are registered with the FastMCP server."""
    tools = await mcp.list_tools()
    # tools is likely a list of Tool objects or dicts. Check names.
    tool_names = [t.name for t in tools] if hasattr(tools[0], 'name') else [t['name'] for t in tools]
    
    assert "boot_fabric" in tool_names
    assert "boot_soc" in tool_names
    assert "boot_soc_ssh" in tool_names
    assert "boot_selmap" in tool_names
    assert "boot_soc_tftp" in tool_names
    assert "provision_software" in tool_names
    assert "run_shell_command" in tool_names
    assert "list_sessions" in tool_names


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_run_strategy_success(mock_get, tmp_path):
    """Test the generic _run_strategy helper function."""
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_strat.boot_log = "Test boot log"
    mock_get.return_value = (mock_tg, mock_strat, "session-123")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    # Define a dummy setup callback
    setup_called = False

    def setup_cb(tg, strat):
        nonlocal setup_called
        setup_called = True
        strat.custom_attr = "value"

    result = _run_strategy(
        str(config),
        target_name="main",
        strategy_driver="TestDriver",
        state="shell",
        session_id=None,
        setup_callback=setup_cb,
    )
    result_json = json.loads(result)

    assert result_json["status"] == "success"
    assert result_json["session_id"] == "session-123"
    assert "Successfully reached state 'shell'" in result_json["message"]
    assert result_json["boot_log"] == "Test boot log"
    mock_strat.transition.assert_called_with("shell")
    assert setup_called
    assert mock_strat.custom_attr == "value"


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_run_strategy_failure(mock_get, tmp_path):
    """Test _run_strategy failure handling."""
    mock_get.side_effect = Exception("Strategy error")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _run_strategy(
        str(config),
        target_name="main",
        strategy_driver="TestDriver",
        state="shell",
        session_id=None,
    )
    result_json = json.loads(result)

    assert result_json["status"] == "fail"
    assert "Strategy error" in result_json["error"]


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_strategy")
async def test_boot_fabric_tool(mock_run):
    """Test boot_fabric tool calls _run_strategy correctly."""
    mock_run.return_value = "{}"
    
    await boot_fabric(
        config_path="conf.yaml",
        bitstream_path="bit.bit",
        kernel_path="uImage",
        target="main",
        state="shell",
    )
    
    args, _ = mock_run.call_args
    assert args[0] == "conf.yaml"
    assert args[1] == "main"
    assert args[2] == "BootFabric"
    assert args[3] == "shell"


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_strategy")
async def test_boot_soc_tool(mock_run):
    """Test boot_soc tool calls _run_strategy correctly."""
    mock_run.return_value = "{}"
    
    await boot_soc(
        config_path="conf.yaml",
        release_version="2023_R2",
        update_image=True,
    )
    
    args, _ = mock_run.call_args
    assert args[2] == "BootFPGASoC"


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_strategy")
async def test_boot_soc_tftp_tool(mock_run):
    """Test boot_soc_tftp tool calls _run_strategy correctly."""
    mock_run.return_value = "{}"
    
    await boot_soc_tftp(
        config_path="conf.yaml",
        tftp_root="/srv/tftp",
        kernel_path="Image",
    )
    
    args, _ = mock_run.call_args
    assert args[2] == "BootFPGASoCTFTP"


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_strategy")
async def test_provision_software_tool(mock_run):
    """Test provision_software tool calls _run_strategy correctly."""
    mock_run.return_value = "{}"
    
    await provision_software(
        config_path="conf.yaml",
        packages=["vim", "git"],
        state="software_installed",
    )
    
    args, _ = mock_run.call_args
    assert args[2] == "SoftwareProvisioningStrategy"
    assert args[3] == "software_installed"


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_run_shell_command_mcp(mock_session_manager):
    # Setup mock session
    mock_env = MagicMock()
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    # Ensure strategy has a shell attribute (mocking the driver)
    mock_shell = MagicMock()
    mock_shell.run.return_value = ("output", "error", 0)
    mock_strat.shell = mock_shell

    mock_session_manager.get_session.return_value = (mock_env, mock_tg, mock_strat)

    # Test execution via async tool wrapper
    result = asyncio.run(run_shell_command(session_id="test-session", command="ls -la"))
    
    mock_session_manager.get_session.assert_called_with("test-session")
    mock_tg.activate.assert_called_with(mock_shell)
    mock_shell.run.assert_called_with("ls -la")
    assert "Return Code: 0" in result
    assert "Stdout:\noutput" in result


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_list_sessions_mcp(mock_session_manager):
    # Setup mock
    mock_session_manager.list_sessions.return_value = {
        "s1": {"target": "main"},
    }

    result = asyncio.run(list_sessions())
    
    assert "s1" in result
    assert "main" in result


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_get_session_info_mcp(mock_session_manager):
    # Setup mock
    mock_session_manager.get_session_details.return_value = {"config": "test.yaml"}

    result = asyncio.run(get_session_info(session_id="s1"))
    
    assert "test.yaml" in result


# --- Resource Tests ---

@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_resource_list_sessions(mock_session_manager):
    mock_session_manager.list_sessions.return_value = {"s1": {"meta": "data"}}
    
    result = asyncio.run(resource_list_sessions())
    assert "s1" in result
    assert "meta" in result

@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_resource_session_info(mock_session_manager):
    mock_session_manager.get_session_details.return_value = {"config": "test.yaml"}
    
    result = asyncio.run(resource_session_info("s1"))
    assert "test.yaml" in result