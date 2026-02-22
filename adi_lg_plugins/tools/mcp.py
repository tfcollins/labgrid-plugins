import asyncio
import json
import logging
import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from fastmcp import FastMCP
from labgrid import Environment

# Initialize FastMCP server
mcp = FastMCP("ADI Labgrid Plugins")


@dataclass
class BootResult:
    """Structured result for boot operations."""

    status: str  # "success" or "fail"
    session_id: str
    message: str
    boot_log: str = ""
    error: str = ""

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), indent=2)


class SessionManager:
    """Manages persistent Labgrid environments for MCP sessions."""

    def __init__(self):
        self.sessions = {}
        self._lock = threading.RLock()

    def create_session(self, config_path: str, target_name: str, strategy_driver: str) -> str:
        """Create a new session and return its ID."""
        with self._lock:
            session_id = str(uuid.uuid4())
            env = Environment(config_path)
            tg = env.get_target(target_name)
            strategy = tg.get_driver(strategy_driver)
            self.sessions[session_id] = {
                "env": env,
                "target": tg,
                "strategy": strategy,
                "meta": {
                    "config_path": config_path,
                    "target_name": target_name,
                    "strategy_driver": strategy_driver,
                    "created_at": str(os.path.getmtime(config_path)),  # Approximate timestamp
                },
            }
            return session_id

    def get_session(self, session_id: str):
        """Retrieve session components by ID."""
        with self._lock:
            if session_id not in self.sessions:
                raise ValueError(f"Session {session_id} not found")
            data = self.sessions[session_id]
            return data["env"], data["target"], data["strategy"]

    def get_session_details(self, session_id: str):
        """Retrieve session metadata."""
        with self._lock:
            if session_id not in self.sessions:
                raise ValueError(f"Session {session_id} not found")
            return self.sessions[session_id]["meta"].copy()

    def list_sessions(self):
        """List all active sessions."""
        with self._lock:
            return {sid: data["meta"].copy() for sid, data in self.sessions.items()}


session_manager = SessionManager()


def _get_target_and_strategy(
    config_path: str, target_name: str, strategy_driver: str, session_id: str | None = None
) -> tuple[object, object, str]:
    """Helper to initialize Labgrid environment and get strategy, optionally using a session."""
    if session_id:
        try:
            _, tg, strategy = session_manager.get_session(session_id)
            return tg, strategy, session_id
        except ValueError:
            pass

    new_session_id = session_manager.create_session(config_path, target_name, strategy_driver)
    _, tg, strategy = session_manager.get_session(new_session_id)
    return tg, strategy, new_session_id


def _run_strategy(
    config_path: str,
    target_name: str,
    strategy_driver: str,
    state: str,
    session_id: str | None,
    setup_callback: Callable[[Any, Any], None] | None = None,
) -> str:
    """
    Generic helper to run a Labgrid strategy transition.

    Args:
        config_path: Path to Labgrid config.
        target_name: Name of the target in config.
        strategy_driver: Name of the strategy driver class.
        state: The target state to transition to.
        session_id: Optional existing session ID.
        setup_callback: Optional function(target, strategy) to configure the strategy/resources before transition.
    """
    boot_log = ""
    active_session_id = ""
    try:
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target_name, strategy_driver, session_id
        )

        if setup_callback:
            setup_callback(tg, strategy)

        strategy.transition(state)
        boot_log = getattr(strategy, "boot_log", "")

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target_name}' using {strategy_driver}.",
            boot_log=boot_log,
        ).to_json()

    except Exception as e:
        # Try to capture partial boot log on failure
        if active_session_id:
            try:
                _, _, strat = session_manager.get_session(active_session_id)
                boot_log = getattr(strat, "boot_log", "")
            except Exception:
                pass

        return BootResult(
            status="fail",
            session_id=active_session_id,
            message="Strategy transition failed",
            boot_log=boot_log,
            error=str(e),
        ).to_json()


# --- Boot Tools ---


@mcp.tool()
async def boot_fabric(
    config_path: str,
    bitstream_path: str | None = None,
    kernel_path: str | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    """
    Boot an FPGA using the JTAG-based BootFabric strategy.

    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        bitstream_path: Optional path to override the FPGA bitstream file (.bit).
        kernel_path: Optional path to override the Linux kernel image (.strip).
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
        session_id: Optional session ID to reuse an existing session.
    """

    def setup(tg, strategy):
        try:
            resource = tg.get_resource("XilinxDeviceJTAG")
            if bitstream_path:
                resource.bitstream_path = os.path.abspath(bitstream_path)
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
        except Exception:
            pass

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "BootFabric", state, session_id, setup
    )


@mcp.tool()
async def boot_soc(
    config_path: str,
    release_version: str | None = None,
    kernel_path: str | None = None,
    bootbin_path: str | None = None,
    devicetree_path: str | None = None,
    target: str = "main",
    state: str = "shell",
    update_image: bool = False,
    session_id: str | None = None,
) -> str:
    """
    Boot an FPGA SoC using the SD Mux-based BootFPGASoC strategy.

    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        release_version: Optional Kuiper release version.
        kernel_path: Optional path to override the kernel file.
        bootbin_path: Optional path to override the BOOT.BIN file.
        devicetree_path: Optional path to override the devicetree file.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
        update_image: Whether to update the full SD card image.
        session_id: Optional session ID to reuse an existing session.
    """

    def setup(tg, strategy):
        try:
            resource = tg.get_resource("KuiperRelease")
            if release_version:
                resource.release_version = release_version
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
            if bootbin_path:
                resource.BOOTBIN_path = os.path.abspath(bootbin_path)
            if devicetree_path:
                resource.device_tree_path = os.path.abspath(devicetree_path)
        except Exception:
            pass

        if update_image:
            strategy.update_image = True

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "BootFPGASoC", state, session_id, setup
    )


@mcp.tool()
async def boot_soc_ssh(
    config_path: str,
    release_version: str | None = None,
    kernel_path: str | None = None,
    bootbin_path: str | None = None,
    devicetree_path: str | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    """
    Boot an FPGA SoC via SSH using the BootFPGASoCSSH strategy.
    """

    def setup(tg, strategy):
        try:
            resource = tg.get_resource("KuiperRelease")
            if release_version:
                resource.release_version = release_version
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
            if bootbin_path:
                resource.BOOTBIN_path = os.path.abspath(bootbin_path)
            if devicetree_path:
                resource.device_tree_path = os.path.abspath(devicetree_path)
        except Exception:
            pass

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "BootFPGASoCSSH", state, session_id, setup
    )


@mcp.tool()
async def boot_selmap(
    config_path: str,
    pre_boot_files: dict[str, str] | None = None,
    post_boot_files: dict[str, str] | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    """
    Boot a dual-FPGA system using the BootSelMap strategy.
    """

    def setup(tg, strategy):
        if pre_boot_files:
            strategy.pre_boot_boot_files = {
                os.path.abspath(k): v for k, v in pre_boot_files.items()
            }
        if post_boot_files:
            strategy.post_boot_boot_files = {
                os.path.abspath(k): v for k, v in post_boot_files.items()
            }

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "BootSelMap", state, session_id, setup
    )


@mcp.tool()
async def boot_soc_tftp(
    config_path: str,
    release_version: str | None = None,
    kernel_path: str | None = None,
    dtb_path: str | None = None,
    tftp_root: str | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    """
    Boot an FPGA SoC using the BootFPGASoCTFTP strategy (TFTP kernel load).

    Args:
        config_path: Path to the Labgrid configuration file.
        release_version: Optional Kuiper release version.
        kernel_path: Optional path to override the kernel file.
        dtb_path: Optional path to override the device tree file.
        tftp_root: Optional path to override the TFTP root directory.
        target: Target name in the configuration.
        state: Target state to transition to.
        session_id: Optional session ID.
    """

    def setup(tg, strategy):
        # Configure TFTP-specific attributes
        if tftp_root:
            strategy.tftp_root_folder = tftp_root

        # Try to configure KuiperRelease resource if present
        try:
            resource = tg.get_resource("KuiperRelease")
            if release_version:
                resource.release_version = release_version
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
            if dtb_path:
                resource.device_tree_path = os.path.abspath(dtb_path)
        except Exception:
            pass

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "BootFPGASoCTFTP", state, session_id, setup
    )


@mcp.tool()
async def provision_software(
    config_path: str,
    packages: list[str] | None = None,
    repos: list[dict[str, str] | list[str]] | None = None,
    build_steps: list[dict[str, str] | list[str]] | None = None,
    test_steps: list[dict[str, str] | list[str]] | None = None,
    target: str = "main",
    state: str = "tested",
    session_id: str | None = None,
) -> str:
    """
    Run the SoftwareProvisioningStrategy to install software, build, and test.

    Args:
        config_path: Path to Labgrid config.
        packages: List of package names to install.
        repos: List of repos to clone. Can be dicts {'url':.., 'dest':..} or lists [url, dest].
        build_steps: List of build commands. Dicts {'cmd':.., 'dir':..} or lists [cmd, dir].
        test_steps: List of test commands. Dicts {'cmd':.., 'dir':..} or lists [cmd, dir].
        target: Target name.
        state: Desired state (e.g., 'software_installed', 'repos_cloned', 'built', 'tested').
        session_id: Session ID.
    """

    def setup(tg, strategy):
        if packages:
            strategy.packages = packages
        if repos:
            strategy.repos = repos
        if build_steps:
            strategy.build_steps = build_steps
        if test_steps:
            strategy.test_steps = test_steps

    return await asyncio.to_thread(
        _run_strategy, config_path, target, "SoftwareProvisioningStrategy", state, session_id, setup
    )


# --- Command Tools ---


def _run_shell_command(session_id: str, command: str) -> str:
    try:
        env, tg, strategy = session_manager.get_session(session_id)

        shell = getattr(strategy, "shell", None)
        if not shell:
            try:
                shell = tg.get_driver("ADIShellDriver")
            except Exception:
                return "Error: No shell driver available in this session."

        if not shell:
            return "Error: No shell driver found."

        logging.info(f"Executing shell command on session {session_id}: {command}")
        tg.activate(shell)
        stdout, stderr, returncode = shell.run(command)

        return f"Return Code: {returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}"
    except Exception as e:
        return f"Error executing command: {str(e)}"


@mcp.tool()
async def run_shell_command(session_id: str, command: str) -> str:
    """
    Run a shell command on the target board using an active session.

    Args:
        session_id: The ID of the session to use (returned by boot tools).
        command: The shell command to execute.
    """
    return await asyncio.to_thread(_run_shell_command, session_id, command)


def _run_ssh_command(session_id: str, command: str) -> str:
    try:
        env, tg, strategy = session_manager.get_session(session_id)

        # Look for SSHDriver specifically
        # Strategies might bind it as 'ssh' or we look up by class name
        ssh = getattr(strategy, "ssh", None)
        if not ssh:
            try:
                ssh = tg.get_driver("SSHDriver")
            except Exception:
                pass

        if not ssh:
            # Maybe NetworkDriver?
            try:
                ssh = tg.get_driver("NetworkDriver")
            except Exception:
                pass

        if not ssh:
            return "Error: No SSH driver found in this session."

        logging.info(f"Executing SSH command on session {session_id}: {command}")
        tg.activate(ssh)
        stdout, stderr, returncode = ssh.run(command)

        return f"Return Code: {returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}"
    except Exception as e:
        return f"Error executing SSH command: {str(e)}"


@mcp.tool()
async def run_ssh_command(session_id: str, command: str) -> str:
    """
    Run an SSH command on the target board using an active session.
    This specifically looks for an SSHDriver in the session.

    Args:
        session_id: The ID of the session to use.
        command: The command to execute via SSH.
    """
    return await asyncio.to_thread(_run_ssh_command, session_id, command)


# --- Info / Resources ---


def _list_sessions() -> dict:
    return session_manager.list_sessions()


@mcp.tool()
async def list_sessions() -> str:
    """List all active sessions and their metadata."""
    return json.dumps(await asyncio.to_thread(_list_sessions), indent=2)


@mcp.resource("labgrid://sessions")
async def resource_list_sessions() -> str:
    """Resource: JSON list of all active sessions."""
    return json.dumps(await asyncio.to_thread(_list_sessions), indent=2)


def _get_session_info(session_id: str) -> dict:
    return session_manager.get_session_details(session_id)


@mcp.tool()
async def get_session_info(session_id: str) -> str:
    """Get detailed information about a specific session."""
    try:
        return json.dumps(await asyncio.to_thread(_get_session_info, session_id), indent=2)
    except ValueError as e:
        return f"Error: {str(e)}"


@mcp.resource("labgrid://sessions/{session_id}")
async def resource_session_info(session_id: str) -> str:
    """Resource: Detailed information about a specific session."""
    try:
        return json.dumps(await asyncio.to_thread(_get_session_info, session_id), indent=2)
    except ValueError:
        return "{}"


def main():
    """Main entry point for the MCP server."""
    # Configure logging to show info level by default
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # Ensure labgrid logger is also at info level
    logging.getLogger("labgrid").setLevel(logging.INFO)

    mcp.run()


if __name__ == "__main__":
    main()
