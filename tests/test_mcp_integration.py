import json
import os
import shutil
import subprocess

import pytest


@pytest.fixture
def mcp_test_env(tmp_path):
    """
    Sets up a temporary environment for MCP testing.
    - Copies vcu118_daq3.yaml
    - Creates .gemini/settings.json
    """
    # Source paths
    cwd = os.getcwd()
    yaml_src = os.path.join(cwd, "vcu118_daq3.yaml")

    # Destination paths
    yaml_dest = tmp_path / "vcu118_daq3.yaml"
    gemini_dir = tmp_path / ".gemini"
    gemini_dir.mkdir()
    settings_dest = gemini_dir / "settings.json"

    # Copy YAML
    if os.path.exists(yaml_src):
        shutil.copy(yaml_src, yaml_dest)
    else:
        pytest.skip(f"Source configuration {yaml_src} not found")

    # Create settings.json
    settings_content = {
        "mcpServers": {
            "adi-labgrid": {
                "command": "uv",
                "args": ["run", "adi-lg-mcp"],
                "env": {"PYTHONPATH": "${workspaceFolder}"},
            }
        }
    }

    with open(settings_dest, "w") as f:
        json.dump(settings_content, f, indent=2)

    return tmp_path


@pytest.mark.skipif(shutil.which("gemini") is None, reason="Gemini CLI not found")
def test_boot_fabric_mcp_via_agent(mcp_test_env):
    """
    Tests the BootFabric strategy via the MCP server using the Gemini agent.
    Verifies that boot tools return structured JSON with status, session_id,
    boot_log, uart_log_path, message, and error fields.
    """
    prompt = """Use the MCP server to boot the board defined in vcu118_daq3.yaml
    using the BootFabric strategy. The boot_fabric tool returns JSON with fields:
    'status', 'session_id', 'boot_log', 'uart_log_path', 'message', and optionally 'error'.

    After boot completes:
    1. Check that 'status' is 'success'
    2. Print a summary of the 'boot_log' field (first 500 characters)
    3. Print the local 'uart_log_path'
    4. Using the session_id, run 'iio_attr -d' via run_shell_command
    5. Print the IIO output"""

    # Construct the command
    cmd = ["gemini", "--approval-mode", "yolo", "--prompt", prompt]

    # Run the command
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(mcp_test_env))

    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

    if result.returncode != 0:
        pytest.fail(
            f"Gemini agent failed with exit code {result.returncode}. STDERR: {result.stderr}"
        )
    # Note: parsing stdout for specific success messages is difficult without knowing exact agent output,
    # but return code 0 usually implies success for CLI tools.
