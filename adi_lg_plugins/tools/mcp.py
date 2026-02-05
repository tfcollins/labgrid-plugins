import json
import os
import uuid
from dataclasses import asdict, dataclass

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

    def create_session(self, config_path: str, target_name: str, strategy_driver: str) -> str:
        """Create a new session and return its ID."""
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
            },
        }
        return session_id

    def get_session(self, session_id: str):
        """Retrieve session components by ID."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        data = self.sessions[session_id]
        return data["env"], data["target"], data["strategy"]

    def get_session_details(self, session_id: str):
        """Retrieve session metadata."""
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        return self.sessions[session_id]["meta"]

    def list_sessions(self):
        """List all active sessions."""
        return {sid: data["meta"] for sid, data in self.sessions.items()}


session_manager = SessionManager()


def _get_target_and_strategy(
    config_path: str, target_name: str, strategy_driver: str, session_id: str | None = None
) -> tuple[object, object, str | None]:
    """Helper to initialize Labgrid environment and get strategy, optionally using a session."""
    if session_id:
        try:
            _, tg, strategy = session_manager.get_session(session_id)
            return tg, strategy, session_id
        except ValueError:
            pass  # Fallback to creating new if not found (or raise error?) -> Let's reuse logic below

    # Create new session if requested (implied by this helper usage pattern usually)
    # But for backward compatibility of simple calls, we might just return ephemeral objects
    # However, to support state, we should probably encourage session usage.

    # If no session_id provided, we create a new ephemeral one but don't store it unless we return it.
    # The tools wrapping this will handle the session_id return.

    # Actually, let's change the helper to always return (tg, strategy, session_id)
    # If session_id input was None, we create a new session.

    new_session_id = session_manager.create_session(config_path, target_name, strategy_driver)
    _, tg, strategy = session_manager.get_session(new_session_id)
    return tg, strategy, new_session_id


def _boot_fabric(
    config_path: str,
    bitstream_path: str | None = None,
    kernel_path: str | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    boot_log = ""
    active_session_id = ""
    try:
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target, "BootFabric", session_id
        )

        try:
            resource = tg.get_resource("XilinxDeviceJTAG")
            if bitstream_path:
                resource.bitstream_path = os.path.abspath(bitstream_path)
            if kernel_path:
                resource.kernel_path = os.path.abspath(kernel_path)
        except Exception:
            pass

        strategy.transition(state)
        boot_log = getattr(strategy, "boot_log", "")

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target}' using BootFabric.",
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
            message="Boot failed",
            boot_log=boot_log,
            error=str(e),
        ).to_json()


@mcp.tool()
def boot_fabric(
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
    return _boot_fabric(config_path, bitstream_path, kernel_path, target, state, session_id)


def _boot_soc(
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
    boot_log = ""
    active_session_id = ""
    try:
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target, "BootFPGASoC", session_id
        )

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

        strategy.transition(state)
        boot_log = getattr(strategy, "boot_log", "")

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target}' using BootFPGASoC.",
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
            message="Boot failed",
            boot_log=boot_log,
            error=str(e),
        ).to_json()


@mcp.tool()
def boot_soc(
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
    return _boot_soc(
        config_path,
        release_version,
        kernel_path,
        bootbin_path,
        devicetree_path,
        target,
        state,
        update_image,
        session_id,
    )


def _boot_soc_ssh(
    config_path: str,
    release_version: str | None = None,
    kernel_path: str | None = None,
    bootbin_path: str | None = None,
    devicetree_path: str | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    boot_log = ""
    active_session_id = ""
    try:
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target, "BootFPGASoCSSH", session_id
        )

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

        strategy.transition(state)
        boot_log = getattr(strategy, "boot_log", "")

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target}' using BootFPGASoCSSH.",
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
            message="Boot failed",
            boot_log=boot_log,
            error=str(e),
        ).to_json()


@mcp.tool()
def boot_soc_ssh(
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

    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        release_version: Optional Kuiper release version.
        kernel_path: Optional path to override the kernel file.
        bootbin_path: Optional path to override the BOOT.BIN file.
        devicetree_path: Optional path to override the devicetree file.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
        session_id: Optional session ID to reuse an existing session.
    """
    return _boot_soc_ssh(
        config_path,
        release_version,
        kernel_path,
        bootbin_path,
        devicetree_path,
        target,
        state,
        session_id,
    )


def _boot_selmap(
    config_path: str,
    pre_boot_files: dict[str, str] | None = None,
    post_boot_files: dict[str, str] | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    boot_log = ""
    active_session_id = ""
    try:
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target, "BootSelMap", session_id
        )

        if pre_boot_files:
            strategy.pre_boot_boot_files = {
                os.path.abspath(k): v for k, v in pre_boot_files.items()
            }
        if post_boot_files:
            strategy.post_boot_boot_files = {
                os.path.abspath(k): v for k, v in post_boot_files.items()
            }

        strategy.transition(state)
        boot_log = getattr(strategy, "boot_log", "")

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target}' using BootSelMap.",
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
            message="Boot failed",
            boot_log=boot_log,
            error=str(e),
        ).to_json()


@mcp.tool()
def boot_selmap(
    config_path: str,
    pre_boot_files: dict[str, str] | None = None,
    post_boot_files: dict[str, str] | None = None,
    target: str = "main",
    state: str = "shell",
    session_id: str | None = None,
) -> str:
    """
    Boot a dual-FPGA system using the BootSelMap strategy.

    Args:
        config_path: Path to the Labgrid configuration file (yaml).
        pre_boot_files: Optional dictionary mapping local paths to remote paths for pre-boot.
        post_boot_files: Optional dictionary mapping local paths to remote paths for post-boot.
        target: Target name in the configuration (default: 'main').
        state: Target state to transition to (default: 'shell').
        session_id: Optional session ID to reuse an existing session.
    """
    return _boot_selmap(config_path, pre_boot_files, post_boot_files, target, state, session_id)


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

        tg.activate(shell)
        stdout, stderr, returncode = shell.run(command)

        return f"Return Code: {returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}"
    except Exception as e:
        return f"Error executing command: {str(e)}"


@mcp.tool()
def run_shell_command(session_id: str, command: str) -> str:
    """
    Run a shell command on the target board using an active session.

    Args:
        session_id: The ID of the session to use (returned by boot tools).
        command: The shell command to execute.
    """
    return _run_shell_command(session_id, command)


def _list_sessions() -> dict:
    return session_manager.list_sessions()


@mcp.tool()
def list_sessions() -> str:
    """
    List all active sessions and their metadata.
    """
    return json.dumps(_list_sessions(), indent=2)


def _get_session_info(session_id: str) -> dict:
    return session_manager.get_session_details(session_id)


@mcp.tool()
def get_session_info(session_id: str) -> str:
    """
    Get detailed information about a specific session.

    Args:
        session_id: The ID of the session to inspect.
    """
    try:
        return json.dumps(_get_session_info(session_id), indent=2)
    except ValueError as e:
        return f"Error: {str(e)}"


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

        tg.activate(ssh)
        stdout, stderr, returncode = ssh.run(command)

        return f"Return Code: {returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}"
    except Exception as e:
        return f"Error executing SSH command: {str(e)}"


@mcp.tool()
def run_ssh_command(session_id: str, command: str) -> str:
    """
    Run an SSH command on the target board using an active session.
    This specifically looks for an SSHDriver in the session.

    Args:
        session_id: The ID of the session to use.
        command: The command to execute via SSH.
    """
    return _run_ssh_command(session_id, command)


def main():
    """Main entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
