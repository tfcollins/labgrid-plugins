import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from adi_lg_plugins.tools.mcp import (
    _boot_fabric,
    _boot_selmap,
    _boot_soc,
    _get_session_info,
    _list_sessions,
    _run_shell_command,
    _run_ssh_command,
    boot_fabric,
    boot_selmap,
    boot_soc,
    get_session_info,
    list_sessions,
    mcp,
    run_shell_command,
    run_ssh_command,
)


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
    mock_strat.boot_log = "Test boot log output"
    mock_get.return_value = (mock_tg, mock_strat, "session-123")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_fabric(str(config), target="main", state="shell")
    result_json = json.loads(result)

    assert result_json["status"] == "success"
    assert result_json["session_id"] == "session-123"
    assert "Successfully reached state 'shell'" in result_json["message"]
    assert result_json["boot_log"] == "Test boot log output"
    assert result_json["error"] == ""
    mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_soc_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_strat.boot_log = "SoC boot log"
    mock_get.return_value = (mock_tg, mock_strat, "session-456")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_soc(str(config), release_version="2023_R2", state="booted")
    result_json = json.loads(result)

    assert result_json["status"] == "success"
    assert result_json["session_id"] == "session-456"
    assert "Successfully reached state 'booted'" in result_json["message"]
    assert result_json["boot_log"] == "SoC boot log"
    mock_strat.transition.assert_called_with("booted")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_selmap_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_strat.boot_log = "SelMap boot log"
    mock_get.return_value = (mock_tg, mock_strat, "session-789")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_selmap(str(config), pre_boot_files={"local.bin": "/boot/remote.bin"})
    result_json = json.loads(result)

    assert result_json["status"] == "success"
    assert result_json["session_id"] == "session-789"
    assert "Successfully reached state 'shell'" in result_json["message"]
    assert result_json["boot_log"] == "SelMap boot log"
    assert mock_strat.pre_boot_boot_files is not None
    mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_mcp_error_handling(mock_get, tmp_path):
    mock_get.side_effect = Exception("Environment error")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_fabric(str(config))
    result_json = json.loads(result)

    assert result_json["status"] == "fail"
    assert result_json["message"] == "Boot failed"
    assert "Environment error" in result_json["error"]


def test_boot_fabric_real(lg_config):
    """
    Test BootFabric with a real configuration file if provided.
    This test runs creating a real Labgrid environment (no mocking).
    """
    if not lg_config:
        pytest.skip("No real configuration file provided (--lg-config)")

    print(f"Running E2E BootFabric test with config: {lg_config}")

    # We pass 'shell' as state to fully exercise the boot process
    result = _boot_fabric(config_path=lg_config, target="main", state="shell")

    print("Result:", result)
    result_json = json.loads(result)

    assert result_json["status"] == "success"
    assert "Successfully reached state 'shell'" in result_json["message"]
    assert result_json["session_id"]

    session_id = result_json["session_id"]
    print(f"Extracted Session ID: {session_id}")
    print(f"Boot log (first 500 chars): {result_json['boot_log'][:500]}")

    # Test shell command execution
    result = _run_shell_command(session_id=session_id, command="uname -a")
    print("Result:", result)
    assert "Return Code: 0" in result


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

    # Test execution
    result = _run_shell_command(session_id="test-session", command="ls -la")

    # Verification
    mock_session_manager.get_session.assert_called_with("test-session")
    mock_tg.activate.assert_called_with(mock_shell)
    mock_shell.run.assert_called_with("ls -la")
    assert "Return Code: 0" in result
    assert "Stdout:\noutput" in result
    assert "Stderr:\nerror" in result


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_list_sessions_mcp(mock_session_manager):
    # Setup mock
    mock_session_manager.list_sessions.return_value = {
        "s1": {"target": "main"},
        "s2": {"target": "aux"},
    }

    result = _list_sessions()
    assert "s1" in result
    assert result["s1"]["target"] == "main"
    assert "s2" in result


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_get_session_info_mcp(mock_session_manager):
    # Setup mock
    mock_session_manager.get_session_details.return_value = {"config": "test.yaml"}

    result = _get_session_info("s1")
    assert "test.yaml" in result["config"]
    mock_session_manager.get_session_details.assert_called_with("s1")


@patch("adi_lg_plugins.tools.mcp.session_manager")
def test_run_ssh_command_mcp(mock_session_manager):
    # Setup mock session
    mock_env = MagicMock()
    mock_tg = MagicMock()
    mock_strat = MagicMock()

    # Mock SSH driver on target via get_driver
    mock_ssh = MagicMock()
    mock_ssh.run.return_value = ("ssh_out", "", 0)
    mock_tg.get_driver.return_value = mock_ssh

    # Strategy has no ssh attr
    del mock_strat.ssh

    mock_session_manager.get_session.return_value = (mock_env, mock_tg, mock_strat)

    result = _run_ssh_command("s1", "uname")

    mock_tg.activate.assert_called_with(mock_ssh)
    mock_ssh.run.assert_called_with("uname")
    assert "ssh_out" in result
    assert "Return Code: 0" in result


# Async handler tests
# These tests use the FunctionTool.run() method which accepts a dict of arguments
# and returns a ToolResult with content[0].text holding the response


def get_result_text(result):
    """Extract text content from a ToolResult object."""
    return result.content[0].text


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._boot_fabric")
async def test_boot_fabric_async_handler(mock_boot_fabric):
    """Test that the async boot_fabric handler correctly wraps the sync function."""
    mock_boot_fabric.return_value = '{"status": "success", "session_id": "test-123"}'

    result = await boot_fabric.run(
        {"config_path": "/path/config.yaml", "target": "main", "state": "shell"}
    )

    assert "success" in get_result_text(result)
    mock_boot_fabric.assert_called_once_with("/path/config.yaml", None, None, "main", "shell", None)


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._boot_soc")
async def test_boot_soc_async_handler(mock_boot_soc):
    """Test that the async boot_soc handler correctly wraps the sync function."""
    mock_boot_soc.return_value = '{"status": "success", "session_id": "test-456"}'

    result = await boot_soc.run(
        {
            "config_path": "/path/config.yaml",
            "release_version": "2023_R2",
            "target": "main",
            "state": "booted",
        }
    )

    assert "success" in get_result_text(result)
    mock_boot_soc.assert_called_once_with(
        "/path/config.yaml", "2023_R2", None, None, None, "main", "booted", False, None
    )


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._boot_selmap")
async def test_boot_selmap_async_handler(mock_boot_selmap):
    """Test that the async boot_selmap handler correctly wraps the sync function."""
    mock_boot_selmap.return_value = '{"status": "success", "session_id": "test-789"}'

    result = await boot_selmap.run(
        {
            "config_path": "/path/config.yaml",
            "pre_boot_files": {"local.bin": "/boot/remote.bin"},
        }
    )

    assert "success" in get_result_text(result)
    mock_boot_selmap.assert_called_once_with(
        "/path/config.yaml", {"local.bin": "/boot/remote.bin"}, None, "main", "shell", None
    )


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_shell_command")
async def test_run_shell_command_async_handler(mock_run_shell):
    """Test that the async run_shell_command handler correctly wraps the sync function."""
    mock_run_shell.return_value = "Return Code: 0\nStdout:\ntest output"

    result = await run_shell_command.run({"session_id": "session-123", "command": "ls -la"})

    assert "Return Code: 0" in get_result_text(result)
    mock_run_shell.assert_called_once_with("session-123", "ls -la")


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._list_sessions")
async def test_list_sessions_async_handler(mock_list):
    """Test that the async list_sessions handler correctly wraps the sync function."""
    mock_list.return_value = {"s1": {"target": "main"}}

    result = await list_sessions.run({})

    assert "s1" in get_result_text(result)
    mock_list.assert_called_once()


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._get_session_info")
async def test_get_session_info_async_handler(mock_get_info):
    """Test that the async get_session_info handler correctly wraps the sync function."""
    mock_get_info.return_value = {"config_path": "test.yaml"}

    result = await get_session_info.run({"session_id": "s1"})

    assert "test.yaml" in get_result_text(result)
    mock_get_info.assert_called_once_with("s1")


@pytest.mark.asyncio
@patch("adi_lg_plugins.tools.mcp._run_ssh_command")
async def test_run_ssh_command_async_handler(mock_run_ssh):
    """Test that the async run_ssh_command handler correctly wraps the sync function."""
    mock_run_ssh.return_value = "Return Code: 0\nStdout:\nssh output"

    result = await run_ssh_command.run({"session_id": "s1", "command": "uname -a"})

    assert "Return Code: 0" in get_result_text(result)
    mock_run_ssh.assert_called_once_with("s1", "uname -a")
