"""Hardware and coordinator discovery for runner setup."""

from __future__ import annotations

import glob
import os
import socket
from pathlib import Path
from typing import Any

from adi_lg_plugins.hw_ci import coordinator as coord_mod


def scan_serial_devices() -> list[str]:
    """Scan and return list of stable serial device symlinks on host."""
    devices = []
    for path in glob.glob("/dev/serial/by-id/*"):
        devices.append(path)
    if not devices:
        for path in glob.glob("/dev/serial/by-path/*"):
            devices.append(path)
    return sorted(devices)


def scan_sdmux_devices() -> list[str]:
    """Scan for attached USB-SD-Mux devices."""
    devices = []
    for path in glob.glob("/dev/sg*"):
        try:
            # Check if device is a multiplexer by name/id
            real = os.path.realpath(path)
            devices.append(real)
        except Exception:
            pass
    return sorted(set(devices))


def check_port_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """Test TCP connectivity to a host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def check_coordinator_reachability(coord: str) -> dict[str, Any]:
    """Check both gRPC and REST bridge reachability on coordinator."""
    endpoint = coord_mod.resolve_coordinator(coord)
    host, port_str = endpoint.split(":", 1)
    grpc_port = int(port_str)

    rest_api = coord_mod._resolve_api(endpoint)
    # Extract REST port from URL (default 8000)
    rest_port = 8000
    if ":" in rest_api.replace("http://", "").replace("https://", ""):
        try:
            rest_port = int(rest_api.split(":")[-1].rstrip("/"))
        except ValueError:
            pass

    grpc_ok = check_port_reachable(host, grpc_port)
    rest_ok = check_port_reachable(host, rest_port)

    return {
        "coordinator": endpoint,
        "host": host,
        "grpc_port": grpc_port,
        "grpc_reachable": grpc_ok,
        "rest_port": rest_port,
        "rest_reachable": rest_ok,
        "rest_api": rest_api,
    }


def validate_direct_env(env_path: Path | str) -> bool:
    """Validate that direct environment YAML file exists and contains valid config."""
    p = Path(env_path).resolve()
    if not p.is_file():
        return False
    try:
        import yaml

        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return isinstance(data, dict) and "targets" in data
    except Exception:
        return False
