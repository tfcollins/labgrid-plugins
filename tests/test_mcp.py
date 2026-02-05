import asyncio
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
    mcp,
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
    mock_get.return_value = (mock_tg, mock_strat, "session-123")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_fabric(str(config), target="main", state="shell")

    assert "Successfully reached state 'shell'" in result
    assert "Session ID: session-123" in result
    mock_strat.transition.assert_called_with("shell")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_soc_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_get.return_value = (mock_tg, mock_strat, "session-456")

    config = tmp_path / "config.yaml"
    config.write_text("targets: {main: {}}")

    result = _boot_soc(str(config), release_version="2023_R2", state="booted")

    assert "Successfully reached state 'booted'" in result
    assert "Session ID: session-456" in result
    mock_strat.transition.assert_called_with("booted")


@patch("adi_lg_plugins.tools.mcp._get_target_and_strategy")
def test_boot_selmap_mcp(mock_get, tmp_path):
    mock_tg = MagicMock()
    mock_strat = MagicMock()
    mock_get.return_value = (mock_tg, mock_strat, "session-789")

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
    assert "Successfully reached state 'shell'" in result
    assert "Session ID: " in result

    # Extract Session ID
    import re

    match = re.search(r"Session ID: ([a-f0-9\-]+)", result)
    assert match, "Could not extract Session ID"
    session_id = match.group(1)
    print(f"Extracted Session ID: {session_id}")

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
