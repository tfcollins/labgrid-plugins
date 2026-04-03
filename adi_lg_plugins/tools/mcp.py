import asyncio
import json
import logging
import math
import os
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from fastmcp import FastMCP
from labgrid import Environment

# Initialize FastMCP server
mcp = FastMCP("ADI Labgrid Plugins")
logger = logging.getLogger(__name__)


@dataclass
class BootResult:
    """Structured result for boot operations."""

    status: str  # "success" or "fail"
    session_id: str
    message: str
    boot_log: str = ""
    uart_log_path: str = ""
    error: str = ""
    uri: str = ""  # IIO URI e.g. "ip:10.0.0.57"
    jesd_status: dict | None = None  # JESD204 link state per interface

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
        """Retrieve session metadata, including target URI if available."""
        with self._lock:
            if session_id not in self.sessions:
                raise ValueError(f"Session {session_id} not found")
            session = self.sessions[session_id]
            meta = session["meta"].copy()
            # Extract current target IP from NetworkService if available
            try:
                tg = session["target"]
                net = tg.get_resource("NetworkService")
                if net and getattr(net, "address", None):
                    meta["uri"] = f"ip:{net.address}"
            except Exception:
                pass
            try:
                strategy = session["strategy"]
                uart_log_path = getattr(strategy, "uart_log_path", "")
                if uart_log_path:
                    meta["uart_log_path"] = uart_log_path
            except Exception:
                pass
            return meta

    def list_sessions(self):
        """List all active sessions."""
        with self._lock:
            result = {}
            for sid in self.sessions:
                result[sid] = self.get_session_details(sid)
            return result


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


def _read_jesd_sysfs(tg: Any, strategy: Any) -> dict | None:
    """Read JESD204 link state from sysfs on the target.

    Reads ``jesd204_fsm_state`` from each JESD RX/TX IIO device found under
    ``/sys/bus/iio/devices/``.  Returns a dict mapping device names to their
    FSM state string (e.g. ``"idle"``, ``"clocks_enable"``, ``"link_setup"``,
    ``"opt_setup_stage{1..5}"``, ``"clocks_enable"``, ``"link_enable"``,
    ``"DATA"``), or *None* if no shell is available.
    """
    shell = getattr(strategy, "shell", None)
    logger.info(
        "JESD sysfs: shell=%r, type=%s",
        shell,
        type(shell).__name__ if shell else "None",
    )
    if not shell:
        return None
    try:
        # Shell should already be active from the strategy transition.
        # Activate only if not already active (idempotent).
        try:
            tg.activate(shell)
        except Exception as ae:
            logger.info("JESD sysfs: activate exception (likely already active): %s", ae)

        # Use a single command that correctly pairs device names with their
        # JESD FSM state.  Only devices that have jesd204_fsm_state are
        # included.  Simple enough for BusyBox serial consoles.
        import time

        cmd = (
            "for d in /sys/bus/iio/devices/iio:device*; do "
            "test -e $d/jesd204_fsm_state && "
            "cat $d/name && cat $d/jesd204_fsm_state; done"
        )

        def _to_lines(out):
            if isinstance(out, list):
                return [line.strip() for line in out if line.strip()]
            if isinstance(out, str):
                return [line.strip() for line in out.strip().splitlines() if line.strip()]
            return []

        # Retry up to 10 times with a 3s delay — the IIO subsystem may take
        # 15-30s to fully load after boot, especially on MicroBlaze.
        lines = []
        for attempt in range(10):
            stdout, _, rc = shell.run(cmd)
            logger.info("JESD sysfs attempt %d: rc=%d, stdout=%r", attempt, rc, stdout)
            lines = _to_lines(stdout) if stdout else []
            if len(lines) >= 2:
                break
            logger.info("JESD sysfs: no output on attempt %d, waiting 3s", attempt)
            time.sleep(3)

        if len(lines) < 2:
            return None

        result = {}
        # Lines come in pairs: name, state
        for i in range(0, len(lines) - 1, 2):
            name = lines[i]
            fsm = lines[i + 1]
            result[name] = fsm

        return result if result else None
    except Exception as e:
        logger.warning("Failed to read JESD sysfs: %s", e)
        return None


def _run_strategy(
    config_path: str,
    target_name: str,
    strategy_driver: str,
    state: str,
    session_id: str | None,
    setup_callback: Callable[[Any, Any], None] | None = None,
    timeout_seconds: float | None = None,
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
        timeout_seconds: Optional maximum wall-clock time to allow the transition.
    """
    boot_log = ""
    uart_log_path = ""
    active_session_id = ""
    try:
        logger.info(
            "Starting strategy '%s' for target '%s' in state '%s' (session=%s)",
            strategy_driver,
            target_name,
            state,
            session_id or "(new)",
        )
        tg, strategy, active_session_id = _get_target_and_strategy(
            config_path, target_name, strategy_driver, session_id
        )

        if setup_callback:
            setup_callback(tg, strategy)

        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        if (
            timeout_seconds is not None
            and strategy_driver == "BootFabric"
            and hasattr(strategy, "wait_for_boot_timeout")
        ):
            strategy.wait_for_boot_timeout = min(
                max(1, math.ceil(timeout_seconds)),
                int(strategy.wait_for_boot_timeout),
            )

        transition_error: Exception | None = None
        transition_traceback = ""

        def _transition() -> None:
            nonlocal transition_error, transition_traceback
            try:
                strategy.transition(state)
            except Exception as exc:  # pragma: no cover - captured for caller
                transition_error = exc
                transition_traceback = traceback.format_exc()

        if timeout_seconds is None:
            _transition()
        else:
            transition_thread = threading.Thread(target=_transition, daemon=True)
            transition_thread.start()
            transition_thread.join(timeout_seconds)
            if transition_thread.is_alive():
                boot_log = getattr(strategy, "boot_log", "")
                uart_log_path = getattr(strategy, "uart_log_path", "")
                return BootResult(
                    status="fail",
                    session_id=active_session_id,
                    message=f"Strategy transition timed out after {timeout_seconds} seconds",
                    boot_log=boot_log,
                    uart_log_path=uart_log_path,
                    error=(
                        f"Timed out waiting for target '{target_name}' to reach state "
                        f"'{state}' using {strategy_driver}"
                    ),
                ).to_json()

        if transition_error is not None:
            if transition_traceback:
                raise RuntimeError(transition_traceback) from transition_error
            raise transition_error

        boot_log = getattr(strategy, "boot_log", "")
        uart_log_path = getattr(strategy, "uart_log_path", "")

        # Extract target IP from the NetworkService resource if available.
        uri = ""
        try:
            net = tg.get_resource("NetworkService")
            if net and getattr(net, "address", None):
                uri = f"ip:{net.address}"
                logger.info("URI from NetworkService: %s", uri)
        except Exception:
            pass

        # If the strategy has a shell, also try reading the actual IP
        # from the target (DHCP may have assigned a different address).
        shell = getattr(strategy, "shell", None)
        if shell:
            try:
                try:
                    tg.activate(shell)
                except Exception:
                    pass
                addrs = shell.get_ip_addresses()
                if addrs:
                    actual_ip = str(addrs[0].ip)
                    logger.info("Actual IP from shell: %s (resource had: %s)", actual_ip, uri)
                    uri = f"ip:{actual_ip}"
            except Exception as e:
                logger.info("Could not read IP from shell: %s", e)

        # Read JESD204 link status from sysfs via the shell if available.
        jesd_status = _read_jesd_sysfs(tg, strategy)

        return BootResult(
            status="success",
            session_id=active_session_id,
            message=f"Successfully reached state '{state}' for target '{target_name}' using {strategy_driver}.",
            boot_log=boot_log,
            uart_log_path=uart_log_path,
            uri=uri,
            jesd_status=jesd_status,
        ).to_json()

    except Exception:
        logger.exception(
            "Strategy transition failed for target '%s' using '%s' in state '%s' (session=%s)",
            target_name,
            strategy_driver,
            state,
            active_session_id or session_id or "(unknown)",
        )

        # Try to capture partial boot log on failure
        if active_session_id:
            try:
                _, _, strat = session_manager.get_session(active_session_id)
                boot_log = getattr(strat, "boot_log", "")
                uart_log_path = getattr(strat, "uart_log_path", "")
            except Exception:
                pass

        return BootResult(
            status="fail",
            session_id=active_session_id,
            message="Strategy transition failed",
            boot_log=boot_log,
            uart_log_path=uart_log_path,
            error=traceback.format_exc(),
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
    timeout_seconds: float = 500,
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
        timeout_seconds: Maximum time to wait for boot success or failure.
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
        _run_strategy,
        config_path,
        target,
        "BootFabric",
        state,
        session_id,
        setup,
        timeout_seconds,
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
